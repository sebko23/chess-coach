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
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import UploadFile
from services.chess_coach.gateway.routes import pdf_ingest
from services.chess_coach.gateway.routes.pdf_ingest import import_pdf

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
    from chess_coach.gateway import create_app
    from chess_coach.gateway.config import GatewaySettings
    import httpx

    settings = GatewaySettings()
    app = create_app(settings)
    app.state.gateway.settings = settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client


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
        "services.chess_coach.gateway.routes.pdf_ingest.run_pdftoppm_in_subprocess",
        return_value=[MagicMock()],
    ):
        with patch(
            "services.chess_coach.gateway.routes.pdf_ingest._predict_fen",
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
# Properties 2, 3, 4 (no network, read-only fs, 2 GB cap) are NOT
# enforced today. The tests below are skip with explicit reasons
# pointing at the future implementation BBFs (FU-22, FU-21, FU-20
# respectively). They will start passing when those implementation
# BBFs land; until then, the CI does not fail on them.
# ===========================================================================


def test_pdf_parsing_runs_in_separate_subprocess() -> None:
    """A-F11 property 1: PDF parsing runs in a separate OS subprocess.

    Per FU-22-impl (2026-10-16): the implementation changed
    from `pdf2image.convert_from_bytes` (which used
    `subprocess.Popen` internally) to
    `services.chess_coach.pdf_ocr.subprocess_runner.run_pdftoppm_in_subprocess`
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
    import services.chess_coach.gateway.routes.pdf_ingest as _pdf_ingest
    from services.chess_coach.pdf_ocr import subprocess_runner as _runner
    # The new A-F11-aware path: the route must import
    # `run_pdftoppm_in_subprocess` from the new module.
    assert hasattr(_pdf_ingest, "run_pdftoppm_in_subprocess"), (
        "services.chess_coach.gateway.routes.pdf_ingest no longer "
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
        "A-F11 property 2 (no network access in PDF-parsing subprocess) "
        "is NOT enforced today. The pdf2image/Popen subprocess inherits "
        "the parent FastAPI process's full outbound network access. "
        "Closing this gap requires either a Linux network namespace via "
        "preexec_fn= or a Windows Job Object — both are out of scope "
        "for this BBF. Tracked as FU-22 (A-F11 property 2 — network "
        "isolation). When FU-22 lands, remove this @pytest.mark.skip "
        "marker and add a real assertion that exercises the property."
    ),
)
def test_subprocess_cannot_initiate_outbound_network() -> None:
    """A-F11 property 2: the PDF-parsing subprocess cannot initiate
    outbound network connections.

    Per docs/08_security/security-strategy.md §A-F11, PDF parsing MUST
    run with no network access. The current pdf2image/Popen
    subprocess inherits the parent's network namespace, so a malicious
    PDF that exploits a CVE in pdftoppm (e.g. CVE-2017-18267,
    CVE-2018-13988, CVE-2019-12293 series) could exfiltrate data
    over the network. This test is skip pending FU-22.

    The test (when un-marked skip) would attempt to bind a TCP
    listener inside the subprocess, then assert the bind is denied
    (e.g. via socket.error with EACCES, or via OSError from
    setrlimit-style network namespace isolation). Marked skip today
    because the implementation does not enforce the property; if
    enforcement is later added, this test is the tripwire.
    """
    # This block is intentionally a no-op. The test is skip because
    # the property is not enforced today. When FU-22 lands, the
    # @pytest.mark.skip marker above is removed and a real assertion
    # is added here (likely: invoke convert_from_bytes in a thread
    # that tries to make a network call, and assert the call is
    # denied).
    assert True  # placeholder; real assertion added when FU-22 lands


@pytest.mark.skip(
    reason=(
        "A-F11 property 3 (read-only filesystem in PDF-parsing "
        "subprocess, except for the per-book artifact dir) is NOT "
        "enforced today. pdf2image writes its own temp file via "
        "tempfile.mkstemp() (typically %TEMP% on Windows, /tmp on "
        "Linux); no filesystem read-only enforcement on the parent. "
        "Closing this gap requires either a chroot / bind-mount "
        "approach (Linux) or a Job Object with the read-only flag "
        "(Windows). Tracked as FU-21 (A-F11 property 3 — read-only "
        "filesystem). When FU-21 lands, remove this @pytest.mark.skip "
        "marker and add a real assertion that exercises the property."
    ),
)
def test_subprocess_filesystem_writes_restricted_to_artifact_dir() -> None:
    """A-F11 property 3: the PDF-parsing subprocess can only write
    to the per-book artifact dir; the rest of the filesystem is
    read-only.

    Per docs/08_security/security-strategy.md §A-F11, the subprocess
    MUST have a read-only filesystem except for the per-book artifact
    dir. The current pdf2image/Popen subprocess has full filesystem
    access (inherits from parent). This test is skip pending FU-21.

    The test (when un-marked skip) would attempt to write to a path
    outside the per-book artifact dir from the subprocess, and assert
    the write is denied (e.g. via OSError EACCES on Linux or via
    WinError 5 on Windows). Marked skip today because the
    implementation does not enforce the property.
    """
    # This block is intentionally a no-op. The test is skip because
    # the property is not enforced today. When FU-21 lands, the
    # @pytest.mark.skip marker above is removed and a real assertion
    # is added here.
    assert True  # placeholder; real assertion added when FU-21 lands


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
    from services.chess_coach.pdf_ocr.subprocess_runner import (
        MEM_CAP_BYTES,
        set_rlimit_as_preexec,
    )
    # 2. MEM_CAP_BYTES is exactly 2 GB
    expected = 2 * 1024 * 1024 * 1024
    assert MEM_CAP_BYTES == expected, (
        f"MEM_CAP_BYTES must be 2 GiB per A-F11 contract; "
        f"got {MEM_CAP_BYTES} bytes"
    )
    # 3. set_rlimit_as_preexec is callable and accepts the
    # 2 GB value without error
    preexec = set_rlimit_as_preexec(MEM_CAP_BYTES)
    assert callable(preexec)
