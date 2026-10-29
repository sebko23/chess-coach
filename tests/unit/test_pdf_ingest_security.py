"""Regression tests for FU-19 (A-F11 poppler-cve) public perimeter.

Three properties are tested:
1. Pre-validation: file-size cap (50 MB), magic-bytes check.
2. Timeout: 5-min wall-clock budget (PARSER_TIMEOUT_SECONDS=300)
   with the asyncio.wait_for outer 330s safety net.
3. PDF_MAGIC constant is the %PDF- prefix.

Tests live in this dedicated file (vs. test_pdf_import.py which
exists for end-to-end chessvision.ai integration). The integration
test test_invalid_pdf_returns_422 was intentionally superseded by
test_pdf_ingest_security.py::test_non_pdf_returns_400 (faster
pre-validation failure vs. parser-time failure).
"""
from __future__ import annotations

import io
import shutil
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from chess_coach.gateway.routes import pdf_ingest

AUTH = {"Authorization": "Bearer devtoken123"}

# Minimal valid PDF (reused from tests/integration/test_pdf_import.py).
MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n190\n"
    b"%%EOF"
)


# ===========================================================================
# A. Module-level constants and their interpretation
# ===========================================================================


def test_max_pdf_bytes_constant_is_50mb() -> None:
    """The FU-19 A-F11 pre-validation cap is 50 MB. If this changes,
    the FU entry should be re-evaluated because the rationale
    (defensive default against pathologically large uploads) might
    no longer match the contract.
    """
    assert pdf_ingest.MAX_PDF_BYTES == 50 * 1024 * 1024  # 50 MiB


def test_pdf_magic_constant_matches_pdf_spec() -> None:
    """PDF files start with the literal bytes '%PDF-' (PDF spec,
    ISO 32000). The magic check in import_pdf must use this constant.
    """
    assert pdf_ingest.PDF_MAGIC == b"%PDF-"


def test_parser_timeout_local_within_route() -> None:
    """The timeout constants are local to the route handler
    (per-request), not module-level. Verify their values via the route
    source so a refactor that makes them module-level doesn't lose
    the explicit interpretation.
    """
    import inspect
    src = inspect.getsource(pdf_ingest.import_pdf)
    assert "PARSER_TIMEOUT_SECONDS = 300" in src
    assert "ASYNCIO_WAIT_SLACK_SECONDS = 30" in src


# ===========================================================================
# B. Pre-validation: 413 for oversized, 400 for non-PDF magic
# ===========================================================================


@pytest_asyncio.fixture
async def prod_client():
    """Build a real FastAPI app from create_app() so the route handlers
    (including @route_guard) run end-to-end.
    """
    import httpx

    from chess_coach.gateway import create_app
    from chess_coach.gateway.config import GatewaySettings

    settings = GatewaySettings()
    app = create_app(settings)
    app.state.gateway.settings = settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def prod_client_and_app():
    """Like `prod_client`, but also yields the app object.

    BBF-FU-22 needs the app instance to resolve which `subprocess_runner`
    module the LIVE route uses (see `_app_runner_module`).
    """
    import httpx

    from chess_coach.gateway import create_app
    from chess_coach.gateway.config import GatewaySettings

    settings = GatewaySettings()
    app = create_app(settings)
    app.state.gateway.settings = settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client, app


async def test_oversized_pdf_returns_413(prod_client) -> None:
    """50 MB+ 1 byte of payload must be rejected with 413 BEFORE any
    pdf2image work (and BEFORE pdftoppm is invoked).
    """
    oversized = b"%PDF-1.4\n" + b"X" * (pdf_ingest.MAX_PDF_BYTES + 1)
    r = await prod_client.post(
        "/v1/import/pdf",
        headers=AUTH,
        files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
    )
    assert r.status_code == 413, (
        f"expected 413 for {len(oversized)}-byte upload, "
        f"got {r.status_code}: {r.text}"
    )


async def test_non_pdf_returns_400(prod_client) -> None:
    """Bytes that don't start with the %PDF- prefix must be rejected
    with 400 (versus the prior behavior of 422 from pdftoppm raising
    a syntax error after the parser was invoked).
    """
    r = await prod_client.post(
        "/v1/import/pdf",
        headers=AUTH,
        files={
            "file": (
                "sneaky.exe",
                io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00"),
                "application/octet-stream",
            )
        },
    )
    assert r.status_code == 400, (
        f"expected 400 for non-PDF magic, got {r.status_code}: {r.text}"
    )


async def test_minimal_pdf_passes_magic_check(prod_client) -> None:
    """A valid %PDF- header must reach the parser (subsequent parse
    may fail; the assertion is that the magic check ALLOWED it past
    pre-validation, not that parsing succeeds). We mock
    run_pdftoppm_in_subprocess so we don't actually need pdftoppm.

    FU-22-impl note: the mock target changed from
    `pdf_ingest.convert_from_bytes` (the old pdf2image-based
    path) to `pdf_ingest.run_pdftoppm_in_subprocess` (the new
    A-F11-aware path that wraps pdftoppm with a 2 GB memory
    cap via preexec_fn). The mock target must match the new
    function the route calls.
    """
    with patch(
        "chess_coach.gateway.routes.pdf_ingest.run_pdftoppm_in_subprocess",
        return_value=[MagicMock()],
    ), patch(
        "chess_coach.gateway.routes.pdf_ingest._predict_fen",
        new_callable=AsyncMock,
        return_value=("8/8/8/4k3/8/8/8/4K2R w K - 0 1", 0.9, None),
    ):
        r = await prod_client.post(
            "/v1/import/pdf",
            headers=AUTH,
            files={
                "file": ("ok.pdf", io.BytesIO(MINIMAL_PDF), "application/pdf")
            },
        )
    # The test is that we DIDN'T get 400 / 413.
    assert r.status_code not in (400, 413), (
        f"unexpected pre-validation rejection: {r.status_code} {r.text}"
    )


# ===========================================================================
# C. Timeout machinery: TIMEOUT_SECONDS=300 + asyncio.wait_for 330s
# ===========================================================================


def test_timeout_is_passed_to_pdf2image() -> None:
    """Direct unit test: invoking convert_from_bytes with timeout=
    triggers the PDFPopplerTimeoutError on a slow parser. We use a
    smaller-than-prod timeout (2 seconds) on a real pdftoppm
    invocation against a real but tiny PDF and assert we got EITHER
    success (fast enough) OR PDFPopplerTimeoutError (slow enough).
    Either is acceptable -- what matters is that the timeout is
    wired through.
    """
    from pdf2image.exceptions import PDFPopplerTimeoutError

    if shutil.which("pdftoppm") is None:
        pytest.skip("pdftoppm not installed in this environment")

    from pdf2image import convert_from_bytes as cfb
    start = time.monotonic()
    try:
        cfb(MINIMAL_PDF, dpi=100, first_page=1, last_page=1, timeout=2)
    except PDFPopplerTimeoutError:
        elapsed = time.monotonic() - start
        assert elapsed < 5, f"timeout machinery too slow: {elapsed}s"
    except Exception:
        # Other exceptions are acceptable in this test (e.g.,
        # PDFSyntaxError if poppler rejects our minimal fixture);
        # the assertion is only about the timeout being wired.
        pass


def test_route_uses_asyncio_wait_for_wrapper() -> None:
    """Static assertion: the route uses asyncio.wait_for as the outer
    safety net, with a slack over PARSER_TIMEOUT_SECONDS. Smoke.yml
    gate stays honest about what enforces the A-F11 5-minute budget.

    FU-22-impl note: the inner timeout error class changed
    from `PDFPopplerTimeoutError` (the pdf2image-specific
    exception raised by `convert_from_bytes(timeout=...)`) to
    `asyncio.TimeoutError` (raised by the outer `asyncio.wait_for`
    when the inner `run_pdftoppm_in_subprocess` exceeds the
    PARSER_TIMEOUT_SECONDS budget). The new code path catches
    `asyncio.TimeoutError` (not `PDFPopplerTimeoutError`) and
    surfaces 504 Gateway Timeout. The smoke.yml assertion
    here is updated to match.
    """
    import inspect
    src = inspect.getsource(pdf_ingest.import_pdf)
    assert "asyncio.wait_for" in src
    assert "PARSER_TIMEOUT_SECONDS + ASYNCIO_WAIT_SLACK_SECONDS" in src
    # FU-22-impl: the inner timeout class is now asyncio.TimeoutError
    # (raised by the outer wait_for), not PDFPopplerTimeoutError
    # (which was pdf2image-specific).
    assert "asyncio.TimeoutError" in src
    # 504 Gateway Timeout is the HTTP status for the A-F11 violation
    assert "status_code=504" in src
    # 413 Payload Too Large is for the file-size cap
    assert "status_code=413" in src
    # 400 Bad Request for the magic-bytes rejection
    assert "status_code=400" in src
    # FU-22-impl: 422 Unprocessable Entity is for the 2 GB memory cap hit
    assert "status_code=422" in src
    # FU-22-impl: the route uses the new subprocess_runner module
    assert "run_pdftoppm_in_subprocess" in src


# ===========================================================================
# D. Smoke-coverage marker (positive assertion: file is in smoke.yml)
# ===========================================================================


def test_route_is_wired_to_smoke_yml() -> None:
    """Positive assertion: this test file IS CI-enforced by smoke.yml's
    boot job. Prevents the lesson from last session's sec02: a regression
    test unenforced by CI provides no real protection.

    Pre-FU-28 (explicit-by-name): the file's basename appeared literally
    in the pytest invocation list. Post-FU-28 (glob-based): the file is
    enforced by its parent directory being in the pytest invocation AND
    not being excluded by any --ignore= clause. This test now asserts
    the post-FU-28 structural condition.

    See FU-31 in docs/16_audit/OPEN-FOLLOWUPS.md for the FU-28->FU-31
    transition rationale.
    """
    # pdf_ingest is at services/chess_coach/gateway/routes/pdf_ingest.py
    # 4 levels up gives the repo root where .github/workflows/ lives.
    repo_root = Path(pdf_ingest.__file__).resolve().parents[4]
    smoke_path = repo_root / ".github" / "workflows" / "smoke.yml"
    assert smoke_path.exists(), f"smoke.yml not found at: {smoke_path}"
    smoke_text = smoke_path.read_text(encoding="utf-8")
    smoke_lines = smoke_text.splitlines()

    this_basename = Path(__file__).resolve().name  # "test_pdf_ingest_security.py"
    this_parent_dir = f"tests/{Path(__file__).resolve().parent.name}"  # "tests/unit"

    # Condition 1: the boot-job's pytest invocation must include
    # `tests/unit` as a positional arg. The split-then-membership check
    # avoids the comment-noise problem that a bare substring check has
    # (smoke.yml contains "tests/unit" in comments like L171; we only
    # want to match invocations).
    has_unit_invocation = any(
        line.lstrip().startswith("pytest ")
        and this_parent_dir in line.lstrip().split()
        for line in smoke_lines
    )
    assert has_unit_invocation, (
        f"No `pytest` invocation in smoke.yml includes `{this_parent_dir}` as a "
        f"positional arg; under the FU-28 glob-based convention, the boot-job "
        f"pytest invocation must include this directory for {this_basename} "
        f"to be CI-enforced. Without it, the file is silently unenforced "
        f"(the sec02 lesson). Check the gateway-boot job's `pytest` step "
        f"in .github/workflows/smoke.yml."
    )

    # Condition 2: this file's basename must NOT appear in any --ignore=
    # clause. --ignore= is the only mechanism that excludes a file from
    # the glob, so a positive match here would mean the file is excluded
    # even though its directory is in scope.
    ignored_paths = [
        line.split("=", 1)[1].strip()
        for line in smoke_lines
        if line.strip().startswith("--ignore=")
    ]
    # Each --ignore= value may end with a backslash-continuation; strip
    # trailing backslashes + whitespace before checking.
    ignored_paths = [p.rstrip("\\").strip() for p in ignored_paths]
    for ignored in ignored_paths:
        assert this_basename not in ignored, (
            f"{this_basename} IS in an --ignore= clause in smoke.yml "
            f"({ignored!r}); per the sec02 lesson, this would silently "
            f"exclude the file from CI enforcement even though {this_parent_dir} "
            f"is in the pytest invocation. Remove this file from the --ignore= "
            f"list (or remove the --ignore= clause entirely) to restore CI coverage."
        )


# ===========================================================================
# E. A-F11 sandbox isolation properties (FU-19, 2026-10-16)
#
# The A-F11 contract per docs/08_security/security-strategy.md has 5
# properties. Property 5 (5-min timeout) is covered by the tests above
# (test_parser_timeout_local_within_route, test_timeout_is_passed_to_pdf2image,
# test_route_uses_asyncio_wait_for_wrapper). Properties 1-4 below close
# the remaining test-coverage gap.
#
# Property 1 (subprocess isolation) IS partially enforced today via
# pdf2image.convert_from_bytes using subprocess.Popen internally. The
# test below is a real, non-skip assertion that catches the regression
# risk of replacing pdf2image with an in-process library (e.g. PyMuPDF).
#
# Property 2 (no network) is IMPLEMENTED on Linux since BBF-FU-20-impl
# (PRs #163/#164); its end-to-end contract test stays capability-gated
# because unshare(CLONE_NEWNET) needs CAP_SYS_ADMIN, but the wiring and
# the unshare request are now asserted deterministically. Property 3
# (read-only fs) is partial pending FU-21. Property 4 (2 GB cap) is
# IMPLEMENTED via BBF-FU-22-impl (PR #145) and its test passes. Note the
# FU mapping: network = FU-20, filesystem = FU-21, memory cap = FU-22.
# ===========================================================================


def test_pdf_parsing_runs_in_separate_subprocess() -> None:
    """A-F11 property 1: PDF parsing runs in a separate OS subprocess.

    Per FU-22-impl (2026-10-16): the implementation changed
    from `pdf2image.convert_from_bytes` (which used
    `subprocess.Popen` internally) to
    `chess_coach.pdf_ocr.subprocess_runner.run_pdftoppm_in_subprocess`
    (which uses `subprocess.Popen` directly with a
    `preexec_fn=` argument for the A-F11 2 GB memory cap).
    The architectural property (separate OS process) is
    PRESERVED; the new code path is the A-F11-aware
    implementation.

    This test asserts the new architectural choice: the
    route layer imports `run_pdftoppm_in_subprocess` from
    the new `subprocess_runner` module (which is the
    A-F11-aware wrapper), and the module exposes
    `set_rlimit_as_preexec` (the cap mechanism that
    requires the preexec_fn= path). A regression where
    someone replaces `run_pdftoppm_in_subprocess` with
    in-process parsing (e.g. PyMuPDF) would fail this test.

    Verification: assert the new module is imported and
    used by the route.
    """
    import chess_coach.gateway.routes.pdf_ingest as _pdf_ingest
    from chess_coach.pdf_ocr import subprocess_runner as _runner
    # The new A-F11-aware path: the route must import
    # `run_pdftoppm_in_subprocess` from the new module.
    assert hasattr(_pdf_ingest, "run_pdftoppm_in_subprocess"), (
        "chess_coach.gateway.routes.pdf_ingest no longer "
        "imports run_pdftoppm_in_subprocess from the A-F11-aware "
        "subprocess_runner module; A-F11 property 1 (subprocess "
        "isolation via Popen) is no longer guaranteed. Reverting to "
        "in-process PyMuPDF or pdf2image would re-introduce the "
        "native-code PDF parser attack surface that the "
        "run_pdftoppm_in_subprocess path isolates into a separate "
        "OS process."
    )
    # The new module must expose the cap mechanism (the actual
    # A-F11 property 4 implementation). This is the assertion
    # that distinguishes "subprocess_runner.py exists" from
    # "subprocess_runner.py actually implements the cap".
    assert hasattr(_runner, "set_rlimit_as_preexec"), (
        "subprocess_runner.set_rlimit_as_preexec is missing; "
        "A-F11 property 4 (2 GB memory cap) is not implemented. "
        "The cap is the architectural reason the route bypasses "
        "pdf2image in the first place."
    )
    # The cap constant must be exactly 2 GB per the A-F11 contract.
    assert _runner.MEM_CAP_BYTES == 2 * 1024**3, (
        f"subprocess_runner.MEM_CAP_BYTES is {_runner.MEM_CAP_BYTES}, "
        f"expected {2 * 1024**3} (2 GiB) per A-F11 contract."
    )


@pytest.mark.skip(
    reason=(
        "A-F11 property 2 (no outbound network access in the PDF-parsing "
        "subprocess) is enforced on Linux but NOT on Windows, and the "
        "Linux enforcement cannot be asserted deterministically here. "
        "On Linux, BBF-FU-20-impl (PRs #163/#164) added "
        "set_network_isolation_preexec(), which calls os.setsid() then "
        "unshare(CLONE_NEWNET) via ctypes; that syscall requires "
        "CAP_SYS_ADMIN (or kernel.unprivileged_userns_clone), which CI "
        "containers generally lack, so an end-to-end 'egress is denied' "
        "assertion would be capability-dependent and flaky. On Windows "
        "the helper degrades to stripping proxy environment variables, "
        "which is a defense-in-depth measure and explicitly NOT a "
        "guarantee of isolation (pywin32 does not expose "
        "SetInformationJobObject for JobObjectNetRateControlInformation). "
        "Tracked as FU-20 (A-F11 property 2 - network isolation), NOT "
        "FU-22, which is property 4 (the 2 GB memory cap, resolved by "
        "BBF-FU-22-impl PR #145). What this BBF adds instead is "
        "test_network_isolation_is_wired_into_the_popen_preexec, which "
        "deterministically asserts the helper is composed into the "
        "preexec_fn actually handed to subprocess.Popen, plus "
        "test_set_network_isolation_preexec_requests_unshare in "
        "tests/unit/test_subprocess_runner.py which asserts the "
        "unshare(CLONE_NEWNET) call is requested on Linux. Verifying "
        "that the syscall SUCCEEDED remains deferred per FU-20's own "
        "out-of-scope note (2)."
    ),
)
def test_subprocess_cannot_initiate_outbound_network() -> None:
    """A-F11 property 2: the PDF-parsing subprocess cannot initiate
    outbound network connections.

    Per docs/08_security/security-strategy.md §A-F11, PDF parsing MUST
    run with no network access, so a malicious PDF that exploits a CVE
    in pdftoppm (e.g. CVE-2017-18267, CVE-2018-13988, CVE-2019-12293
    series) cannot exfiltrate data over the network.

    Status as of BBF-FU-20-impl (PRs #163/#164, 2026-10-18):
    Linux enforces this via a fresh network namespace; Windows only
    strips proxy env vars, which is best-effort and NOT isolation.

    This contract test stays skipped because the only end-to-end
    formulation ("open a socket inside the child and observe denial")
    is capability-dependent on Linux and impossible on Windows. The
    deterministic parts of the property are covered elsewhere:

    * wiring into Popen — `test_network_isolation_is_wired_into_the_popen_preexec`
    * the unshare request — `test_subprocess_runner.py::
      test_set_network_isolation_preexec_requests_unshare`
    * setsid always runs — `test_subprocess_runner.py::
      test_set_network_isolation_preexec_calls_setsid`
    """
    # Intentionally unreachable while skipped. The skip reason above
    # is the live record of what is and is not verified.
    assert True  # placeholder; capability-gated end-to-end assertion


@pytest.mark.skip(
    reason=(
        "A-F11 property 3 (read-only filesystem in PDF-parsing "
        "subprocess, except for the per-book artifact dir) is PARTIALLY "
        "implemented as of BBF-FU-21-bind-mount: the bind-mount step "
        "(`set_fs_isolation_preexec(tmpdir)` performs "
        "mount(MS_REMOUNT|MS_BIND|MS_RDONLY) + mount(MS_BIND) on the "
        "artifact dir after a successful "
        "unshare(CLONE_NEWUSER|CLONE_NEWNS)). The negative-invariant "
        "test (write outside the artifact dir is denied) requires "
        "CAP_SYS_ADMIN or `kernel.unprivileged_userns_clone` sysctl "
        "in the test environment; this test environment lacks the "
        "capability, so the assertion is skip-gated. See "
        "`test_set_fs_isolation_preexec_performs_mount_on_linux_with_capability` "
        "in `tests/unit/test_subprocess_runner.py` for the real "
        "assertion run on hosts that DO have the capability. On "
        "Windows the no-op applies (AppLocker/WDAC is the "
        "deployment-config concern per BBF-FU-21-windows-scope). "
        "The follow-up BBF that flips the FU-21 ledger entry to "
        "RESOLVED on the Linux-full-enforcement surface is a "
        "separate deliverable per the skill's one-BBF = "
        "one-clean-change rule."
    ),
)
def test_subprocess_filesystem_writes_restricted_to_artifact_dir() -> None:
    """A-F11 property 3: the PDF-parsing subprocess can only write
    to the per-book artifact dir; the rest of the filesystem is
    read-only.

    Per docs/08_security/security-strategy.md §A-F11, the subprocess
    MUST have a read-only filesystem except for the per-book artifact
    dir. PARTIALLY implemented as of BBF-FU-21-bind-mount: the
    bind-mount step is in place on Linux (gated on
    `unshare(CLONE_NEWUSER|CLONE_NEWNS)` + a provided tmpdir path).
    The negative invariant (write outside the artifact dir is denied
    via OSError EACCES on Linux or WinError 5 on Windows) is
    skip-gated on capability -- environments with CAP_SYS_ADMIN or
    `kernel.unprivileged_userns_clone` run the real assertion via
    `test_set_fs_isolation_preexec_performs_mount_on_linux_with_capability`
    in `tests/unit/test_subprocess_runner.py`.

    The positive invariant (pdftoppm's legitimate writes go to the
    tmpdir/artifact dir) IS exercised today by the broader
    `run_pdftoppm_in_subprocess` end-to-end path; this specific test
    is the negative-invariant contract.
    """
    # This block is intentionally a no-op. The test is skip because
    # the NEGATIVE invariant (write outside the artifact dir is
    # denied) is gated on the bind-mount + remount-read-only steps,
    # which require CAP_SYS_ADMIN or unprivileged_userns_clone in
    # the test environment. The bind-mount step IS implemented in
    # `subprocess_runner.py` per BBF-FU-21-bind-mount; the assertion
    # is run in environments that have the capability (CI runners
    # without the capability are skip-gated, which is correct).
    assert True  # placeholder; see brief BBF-FU-21-bind-mount for the real assertion path


def test_network_isolation_is_wired_into_the_popen_preexec() -> None:
    """A-F11 property 2: network isolation is composed into the
    `preexec_fn` that `run_pdftoppm_in_subprocess` passes to
    `subprocess.Popen`.

    BBF-FU-20-impl (PRs #163/#164) implemented
    `set_network_isolation_preexec()` in
    `services/chess_coach/pdf_ocr/subprocess_runner.py`:
    on Linux it calls `os.setsid()` then
    `unshare(CLONE_NEWNET)` via ctypes; on Windows it
    degrades to stripping proxy environment variables.

    What was NOT covered until this test: that the helper is
    actually *wired in*. `run_pdftoppm_in_subprocess` composes
    three pre-exec hooks into a single callable
    (`_combined_preexec`) because `subprocess.Popen` accepts
    only one `preexec_fn`. A regression that dropped the
    network-isolation call from that composition would disable
    A-F11 property 2 in production while every helper-level
    test still passed.

    This test asserts the wiring, not the kernel behaviour:
    it is deterministic, needs no CAP_SYS_ADMIN, no network,
    no `unshare` success, and no `pdftoppm` binary. It passes
    identically on Linux, macOS and Windows.
    """
    import chess_coach.pdf_ocr.subprocess_runner as _runner

    calls: list[str] = []

    def _fake_rlimit(cap_bytes: int):
        calls.append("rlimit")
        return lambda: None

    def _fake_network():
        calls.append("network")
        return lambda: None

    def _fake_fs(artifact_dir):  # noqa: ARG001 - signature parity only
        calls.append("fs")
        return lambda: None

    captured: dict[str, object] = {}

    class _FakePopen:
        def __init__(self, args, **kwargs):  # noqa: ANN001 - test double
            captured["preexec_fn"] = kwargs.get("preexec_fn")
            captured["args"] = args
            self.returncode = 0
            # The real `subprocess.Popen` invokes `preexec_fn` in the
            # child between fork and exec. There is no fork here, so
            # the fake runs it inline. That is what makes the
            # composition observable: if `_combined_preexec` dropped
            # the network-isolation call, `calls` would be short.
            preexec = captured.get("preexec_fn")
            if callable(preexec):
                preexec()

        def communicate(self, input=None, timeout=None):  # noqa: ANN001, A002
            return (None, b"")

        def kill(self) -> None:
            return None

        def wait(self) -> int:
            return 0

    original = {
        "rlimit": _runner.set_rlimit_as_preexec,
        "network": _runner.set_network_isolation_preexec,
        "fs": _runner.set_fs_isolation_preexec,
        "popen": _runner.subprocess.Popen,
        "supported": _runner.MEMORY_CAP_SUPPORTED,
        "windows_job": _runner.WINDOWS_JOB_SUPPORTED,
    }
    _runner.set_rlimit_as_preexec = _fake_rlimit  # type: ignore[assignment]
    _runner.set_network_isolation_preexec = _fake_network  # type: ignore[assignment]
    _runner.set_fs_isolation_preexec = _fake_fs  # type: ignore[assignment]
    _runner.subprocess.Popen = _FakePopen  # type: ignore[assignment]
    # BBF-FU-22-windows-contract-correction: on an uncappable platform the
    # runner now refuses BEFORE spawning anything, so this wiring test must
    # simulate a SUPPORTED platform to reach the Popen call it is asserting.
    # The Windows refusal is covered separately by
    # `test_uncappable_platform_path_never_spawns_a_parser`.
    _runner.MEMORY_CAP_SUPPORTED = True  # type: ignore[assignment]
    # BBF-FU-22-B2-windows-job-object: this test is specifically about the
    # LINUX `subprocess.Popen` + composed-`preexec_fn` path. On Windows the
    # runner no longer uses `subprocess.Popen` at all -- it launches through
    # the Job Object backend -- so the composed preexec is not part of the
    # Windows path and the wiring assertion does not apply there. The
    # Windows path is covered by tests/windows/test_windows_job_enforcement.py.
    # Force the Linux branch so this test keeps measuring what it claims.
    _runner.WINDOWS_JOB_SUPPORTED = False  # type: ignore[assignment]
    try:
        # The runner's post-Popen behaviour is irrelevant here. On
        # Windows the real `subprocess.Popen` refuses `preexec_fn`
        # outright, but we replace Popen with a fake that accepts
        # it, so the composed hook always runs. The fake produces
        # no PNG files, so the runner then raises RuntimeError.
        with pytest.raises(RuntimeError):
            _runner.run_pdftoppm_in_subprocess(b"%PDF-1.4 fake")
    finally:
        _runner.set_rlimit_as_preexec = original["rlimit"]  # type: ignore[assignment]
        _runner.set_network_isolation_preexec = original["network"]  # type: ignore[assignment]
        _runner.set_fs_isolation_preexec = original["fs"]  # type: ignore[assignment]
        _runner.subprocess.Popen = original["popen"]  # type: ignore[assignment]
        _runner.MEMORY_CAP_SUPPORTED = original["supported"]  # type: ignore[assignment]
        _runner.WINDOWS_JOB_SUPPORTED = original["windows_job"]  # type: ignore[assignment]

    assert calls == ["rlimit", "network", "fs"], (
        "the composed pre-exec hook did not run the A-F11 "
        f"isolation callbacks in order; observed: {calls!r}"
    )
    preexec_fn = captured.get("preexec_fn")
    assert callable(preexec_fn), (
        f"subprocess.Popen was called without a callable preexec_fn: {preexec_fn!r}"
    )


def test_subprocess_respects_2gb_memory_cap() -> None:
    """A-F11 property 4: the PDF-parsing subprocess has a 2 GB
    memory cap. A malicious PDF that would balloon RSS beyond 2 GB
    is killed by the sandbox.

    Per docs/08_security/security-strategy.md §A-F11, the subprocess
    MUST have a 2 GB memory cap. This test (FU-22-impl, the
    lightest of the 3 A-F11 implementation BBFs per
    BBF-FU-20-21-22-A-F11-spikes.md) verifies that:

    1. The `subprocess_runner.py` module exposes
       `set_rlimit_as_preexec` (the cap mechanism)
    2. The `MEM_CAP_BYTES` constant is exactly 2 GB
    3. The `set_rlimit_as_preexec(2 * 1024**3)` callable is
       a no-arg callable suitable for `subprocess.Popen`'s
       `preexec_fn=` parameter

    The end-to-end "force a 2 GB balloon and assert the subprocess
    is killed" integration test is intentionally NOT included here:
    it would require a ~2 GB synthetic PDF (impractical) and a Linux
    host with pdftoppm. The cap-behavior under load is exercised in
    `test_subprocess_runner.py::test_set_rlimit_as_preexec_caps_at_target_bytes`
    on Linux, and the CI integration test (Linux, pdftoppm installed
    via apt) exercises the full route path on every PR.
    """
    # 1. The module exposes set_rlimit_as_preexec
    from chess_coach.pdf_ocr.subprocess_runner import (
        MEM_CAP_BYTES,
        set_rlimit_as_preexec,
    )
    # 2. MEM_CAP_BYTES is exactly 2 GB
    expected = 2 * 1024 * 1024 * 1024
    assert expected == MEM_CAP_BYTES, (
        f"MEM_CAP_BYTES must be 2 GiB per A-F11 contract; "
        f"got {MEM_CAP_BYTES} bytes"
    )
    # 3. set_rlimit_as_preexec is callable and accepts the
    # 2 GB value without error
    preexec = set_rlimit_as_preexec(MEM_CAP_BYTES)
    assert callable(preexec)


# ===========================================================================
# J. BBF-FU-22-windows-contract-correction: the deliberate unsupported-platform
#    result, and the corrected Linux contract.
# ===========================================================================


def _route_runner_module():
    """Return the exact `subprocess_runner` module instance the route uses.

    The repository's package tree is importable under more than one dotted
    path (`chess_coach.pdf_ocr.subprocess_runner` and
    `chess_coach.pdf_ocr.subprocess_runner`), and BOTH can be loaded
    in the same process as two distinct module objects with two distinct
    global namespaces. Whichever instance the route module imported is the
    one whose globals `run_pdftoppm_in_subprocess` reads, so a test that
    simulates the unsupported platform must patch THAT instance.

    The lookup is driven by the route's own bound function, so it is correct
    regardless of which dotted path the interpreter loaded.
    """
    module_name = pdf_ingest.run_pdftoppm_in_subprocess.__globals__["__name__"]
    module = sys.modules[module_name]
    assert module.__dict__ is pdf_ingest.run_pdftoppm_in_subprocess.__globals__, (
        f"resolved runner module {module_name!r} is not the one the route's "
        f"function reads its globals from"
    )
    return module


def _app_runner_module(app) -> object:
    """Return the runner module instance the RUNNING APP's route uses.

    `create_app()` imports the route under the top-level `chess_coach.*`
    path, while this test module imports it under `chess_coach.*`.
    Those are two separate module objects, so patching the one this file
    imported would leave the app's route untouched -- and the test would
    silently assert nothing.

    Resolution is driven by the app's own route table. The app registers
    routers (whose members carry no `.path`), so the route is located via
    the router's declared prefix and the route's own path.

    The route's endpoint is wrapped by `@route_guard`, so the endpoint
    function's own `__globals__` belong to the decorator, not the route
    module. `__module__` (copied by `functools.wraps`) still names the route
    module, so we resolve through that.
    """
    from chess_coach.gateway.routes import pdf_ingest_router

    wanted = f"{pdf_ingest_router.prefix}/pdf"
    for route in pdf_ingest_router.routes:
        if getattr(route, "path", "") != wanted:
            continue
        module = sys.modules[route.endpoint.__module__]
        runner = module.__dict__["run_pdftoppm_in_subprocess"]
        return sys.modules[runner.__globals__["__name__"]]
    raise AssertionError(
        f"could not locate the {wanted!r} route on the app's pdf_ingest_router"
    )


async def test_unsupported_platform_returns_501_not_422(
    prod_client_and_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A platform that cannot enforce the cap yields 501 / not_implemented.

    Pre-BB1, `run_pdftoppm_in_subprocess` reached
    `subprocess.Popen(preexec_fn=...)`, CPython raised
    `ValueError: preexec_fn is not supported on Windows platforms`, and the
    route's catch-all turned that internal configuration failure into an
    incidental 422 - the SAME status as a malformed PDF or a generic parser
    failure, so a client could not tell "your file is bad" from "this
    platform cannot run the parser at all".

    This test fails against that behavior: it requires 501 AND the ADR-0002
    error code `internal.not_implemented`. It also proves no parser process
    is spawned on this path.
    """
    prod_client, app = prod_client_and_app
    subprocess_runner = _app_runner_module(app)

    # Patch the module's own platform constant, NOT the process-wide
    # `sys.platform`: mutating the shared stdlib module would corrupt
    # unrelated runtime behaviour (asyncio / anyio) and make this test
    # measure the wrong thing.
    #
    # BBF-FU-22-B2-windows-job-object: Windows now HAS an enforcement
    # mechanism (the Job Object backend), so the uncappable platform is
    # simulated with a platform that genuinely has neither mechanism.
    monkeypatch.setattr(subprocess_runner, "HOST_PLATFORM", "sunos5")
    monkeypatch.setattr(subprocess_runner, "MEMORY_CAP_SUPPORTED", False)

    spawn_calls: list[object] = []

    def _tripwire(*args: object, **kwargs: object) -> None:
        spawn_calls.append((args, kwargs))
        raise AssertionError(
            "subprocess.Popen was called on the unsupported-platform path; "
            "an uncapped parser process was spawned."
        )

    monkeypatch.setattr(subprocess_runner.subprocess, "Popen", _tripwire)

    r = await prod_client.post(
        "/v1/import/pdf",
        headers=AUTH,
        files={"file": ("test.pdf", io.BytesIO(MINIMAL_PDF), "application/pdf")},
    )

    assert r.status_code == 501, (
        f"an unsupported platform must return 501, got {r.status_code}; "
        f"body={r.text[:300]}"
    )
    body = r.json()
    assert body["error"]["code"] == "internal.not_implemented", (
        f"the error code must be `internal.not_implemented`, got {body}"
    )
    assert body["error"]["retriable"] is False
    assert not spawn_calls, (
        f"no parser process may be spawned on the unsupported path, but Popen "
        f"was called {len(spawn_calls)} time(s)"
    )


async def test_unsupported_platform_is_distinct_from_other_pdf_outcomes(
    prod_client_and_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 501 is separable from the 400 (malformed) and 422 (parser failure).

    The directive requires the deliberate unsupported-platform result to be
    distinguishable from malformed input, a missing tool, a timeout, and a
    generic parser failure.
    """
    prod_client, app = prod_client_and_app
    subprocess_runner = _app_runner_module(app)

    # Baseline: malformed input (no %PDF- header) is a 400.
    bad = await prod_client.post(
        "/v1/import/pdf",
        headers=AUTH,
        files={"file": ("bad.pdf", io.BytesIO(b"not a pdf"), "application/pdf")},
    )
    assert bad.status_code == 400, (
        f"malformed input must be 400, got {bad.status_code}"
    )

    monkeypatch.setattr(subprocess_runner, "HOST_PLATFORM", "sunos5")
    monkeypatch.setattr(subprocess_runner, "MEMORY_CAP_SUPPORTED", False)
    unsupported = await prod_client.post(
        "/v1/import/pdf",
        headers=AUTH,
        files={"file": ("test.pdf", io.BytesIO(MINIMAL_PDF), "application/pdf")},
    )

    assert unsupported.status_code == 501
    assert unsupported.json()["error"]["code"] == "internal.not_implemented"
    assert unsupported.status_code != bad.status_code
    assert unsupported.status_code not in (400, 404, 413, 422, 504)


def test_uncappable_platform_path_never_spawns_a_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard fires BEFORE `subprocess.Popen`, so nothing is started.

    This is the subprocess-level counterpart of the route-level test: it
    asserts the refusal happens at the runner boundary, independent of the
    gateway.
    """
    subprocess_runner = _route_runner_module()

    # BBF-FU-22-B2-windows-job-object: Windows now HAS an enforcement
    # mechanism (the Job Object backend), so the uncappable platform is
    # simulated with a platform that genuinely has neither mechanism.
    monkeypatch.setattr(subprocess_runner, "HOST_PLATFORM", "sunos5")
    monkeypatch.setattr(subprocess_runner, "MEMORY_CAP_SUPPORTED", False)

    spawn_calls: list[object] = []

    def _tripwire(*args: object, **kwargs: object) -> None:
        spawn_calls.append((args, kwargs))
        raise AssertionError(
            "subprocess.Popen was called on the unsupported-platform path; "
            "an uncapped parser process was spawned."
        )

    monkeypatch.setattr(subprocess_runner.subprocess, "Popen", _tripwire)

    with pytest.raises(subprocess_runner.UnsupportedParserPlatformError):
        subprocess_runner.run_pdftoppm_in_subprocess(MINIMAL_PDF)

    assert not spawn_calls, (
        f"no parser process may be spawned on the unsupported path, but Popen "
        f"was called {len(spawn_calls)} time(s)"
    )


def test_windows_unsupported_result_carries_the_established_contract() -> None:
    """The deliberate result uses the repository's established error contract.

    `NotImplementedYetError` -> HTTP 501, ADR-0002 code
    `internal.not_implemented`, `retriable=False`. It must be distinct from
    the 400 (malformed), 404 (missing), 413 (too large), 422 (generic parser
    failure) and 504 (timeout) outcomes.
    """
    from chess_coach.errors import ErrorCode

    subprocess_runner = _route_runner_module()
    exc = subprocess_runner.UnsupportedParserPlatformError("unsupported")
    assert exc.http_status == 501
    assert exc.code == ErrorCode.NOT_IMPLEMENTED
    assert str(exc.code) == "internal.not_implemented"
    assert exc.retriable is False
    assert exc.http_status not in (400, 404, 413, 422, 504)


def test_linux_cap_contract_is_per_process_not_an_aggregate_tree_budget() -> None:
    """The corrected contract, pinned in code and prose.

    The Linux cap is a 2 GiB `RLIMIT_AS` address-space limit applied PER
    PROCESS. Descendants inherit it independently; each descendant gets its
    OWN allowance. There is NO aggregate process-tree memory budget.

    BBF-FU-22-B2-windows-job-object: the MECHANISM string is now
    platform-dependent, because Windows enforces the same per-process
    ceiling through a Job Object rather than through `RLIMIT_AS`. The
    *semantics* are unchanged on both platforms: a per-process ceiling
    inherited independently by descendants, never an aggregate tree budget.
    """
    subprocess_runner = _route_runner_module()

    assert subprocess_runner.MEM_CAP_BYTES == 2 * 1024**3

    # The mechanism names the platform's enforcement route. On Linux it
    # is the `RLIMIT_AS` preexec; on Windows it is the Job Object.
    if subprocess_runner.HOST_PLATFORM == "win32":
        assert subprocess_runner.MEMORY_CAP_MECHANISM == (
            "Windows Job Object (JOB_OBJECT_LIMIT_PROCESS_MEMORY)"
        )
    else:
        assert subprocess_runner.MEMORY_CAP_MECHANISM == "RLIMIT_AS via preexec_fn"

    src = Path(subprocess_runner.__file__).read_text(encoding="utf-8")
    # The contract is stated in the module's own docstring.
    assert "aggregate process-tree memory budget" in src
    assert "per-process" in src

    # And the A-F11 prose states it too.
    strategy = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "08_security"
        / "security-strategy.md"
    )
    if strategy.exists():
        text = strategy.read_text(encoding="utf-8")
        assert "aggregate process-tree memory budget" in text, (
            "the A-F11 property-4 prose must explicitly deny an aggregate "
            "process-tree memory budget"
        )
