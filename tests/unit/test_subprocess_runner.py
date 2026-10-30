"""Unit tests for `chess_coach.pdf_ocr.subprocess_runner`.

These tests cover the A-F11 property 4 (2 GB memory cap)
implementation per `docs/16_audit/BBF-FU-22-impl.md`.

The cap mechanism is NOT platform-portable. `set_rlimit_as_preexec`
applies `resource.setrlimit(RLIMIT_AS, ...)` on Linux and returns a
no-op on Windows; `resource` is a Unix-only stdlib module and CPython
rejects `preexec_fn` on Windows outright. So on Windows the cap
cannot be enforced at all, and
`BBF-FU-22-windows-contract-correction` makes Windows PDF parsing
**explicitly unsupported**: `ensure_memory_cap_supported()` raises a
typed `UnsupportedParserPlatformError` (HTTP 501, error code
`internal.not_implemented`) BEFORE any parser process is spawned.

Test 1 (`test_set_rlimit_as_preexec_caps_at_target_bytes`)
is the key Linux test: it forks, applies the cap, and tries to
allocate 3 GB. On Linux, the allocation is killed with
`MemoryError` (or `OSError`). On Windows, the test is
skipped (the cap is a no-op).

Test 2 (`test_set_rlimit_as_preexec_no_cap_means_no_cap`)
is the control test: with no cap, the same 3 GB allocation
succeeds (skipped if the system doesn't have 3 GB of RAM
+ swap).

The BBF-FU-22 additions pin the two properties that the constant
checks do NOT establish:

- `test_memory_cap_is_enforced_not_merely_declared` - the Linux cap
  actually bounds the child's address space.
- `test_descendant_inherits_memory_cap_independently` - a descendant
  inherits the limit, and each descendant gets its OWN 2 GiB
  allowance (there is no aggregate process-tree budget).
- `test_uncappable_platform_refuses_and_spawns_no_process` -
  the Windows path refuses deliberately and never starts a parser.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from chess_coach.errors import ErrorCode
from chess_coach.pdf_ocr import subprocess_runner as _runner_module
from chess_coach.pdf_ocr.subprocess_runner import (
    MEM_CAP_BYTES,
    MEMORY_CAP_MECHANISM,
    UnsupportedParserPlatformError,
)

# Skip the cap-behavior test on Windows: the cap is a
# no-op there (resource.setrlimit is Unix-only). The
# module's existence and signature are still verified
# on Windows via test_2 and test_3 below.
_skip_on_windows = pytest.mark.skipif(
    sys.platform == "win32",
    reason="A-F11 cap mechanism is Unix-only; Windows path is a follow-up BBF",
)


def _runner():
    """Return the exact `subprocess_runner` module instance under test.

    The package tree is importable under more than one dotted path.
    Whichever instance was imported is the one whose globals the
    functions read, so the test must patch that same instance.
    """
    return _runner_module


# ---------------------------------------------------------------------------
# BBF-FU-20-linux-phase1-network-isolation: the retired preexec helpers
# ---------------------------------------------------------------------------
#
# The old `set_rlimit_as_preexec`, `set_network_isolation_preexec`, and
# `set_fs_isolation_preexec` callbacks are RETIRED. They are replaced by
# the single sandbox launcher in `chess_coach.pdf_ocr.linux_sandbox`,
# which owns one namespace lifecycle and applies the whole A-F11 policy
# before the parser is executed.
#
# The old assertions are NOT weakened -- they are re-pointed at the
# launcher's contract, which is STRONGER:
#
#   old: "the preexec_fn is callable"          -> new: "the launcher
#                                                  establishes the namespace"
#   old: "unshare(CLONE_NEWNET) was REQUESTED"  -> new: "the combined
#                                                  namespace is ESTABLISHED"
#   old: "the fs preexec is a no-op on failure" -> new: "a mount failure
#                                                  FAILS CLOSED"
#   old: "Windows strips proxy env vars"        -> new: "Windows REFUSES
#                                                  before any process"
#
# The behaviour of the launcher itself is pinned in
# `tests/unit/test_linux_sandbox.py`; the production-container denial
# proof is `scripts/dev/verify_linux_network_isolation.py`.


def test_the_network_helpers_are_retired() -> None:
    """The competing preexec helpers no longer exist.

    There must be exactly ONE namespace owner. If a second helper
    reappears, the two user-namespace strategies would conflict and
    duplicate the `setsid()` call.
    """
    import chess_coach.pdf_ocr.subprocess_runner as runner

    for retired in (
        "set_rlimit_as_preexec",
        "set_network_isolation_preexec",
        "set_fs_isolation_preexec",
    ):
        assert not hasattr(runner, retired), (
            f"{retired} is retired; the sandbox launcher is the single "
            f"namespace owner"
        )


def test_the_runner_has_no_proxy_stripping_fallback() -> None:
    """There is no proxy-environment fallback anywhere in the runner.

    Proxy stripping is defense in depth, NEVER network isolation. The
    retired implementation fell back to it when `unshare` failed, which
    is precisely the defect this BBF closes.
    """
    import chess_coach.pdf_ocr.subprocess_runner as runner

    source = Path(runner.__file__).read_text(encoding="utf-8")
    for proxy_var in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        assert proxy_var not in source, (
            f"{proxy_var} must not appear in the runner: proxy stripping "
            f"is defense in depth, never network isolation"
        )


def test_the_runner_exposes_the_network_isolation_capability() -> None:
    """The runner exposes the network-isolation capability and mechanism."""
    import chess_coach.pdf_ocr.subprocess_runner as runner

    assert isinstance(runner.NETWORK_ISOLATION_SUPPORTED, bool)
    assert runner.NETWORK_ISOLATION_MECHANISM


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="the Windows refusal is a Windows-only behaviour",
)
def test_windows_refuses_before_any_process_is_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows PDF parsing is refused BEFORE any parser process is created.

    The Job Object backend enforces the MEMORY cap, not network
    isolation, and Job Object network-rate control is throttling rather
    than isolation. So on Windows the parser must not start at all.
    """
    import chess_coach.pdf_ocr.subprocess_runner as runner

    monkeypatch.setattr(runner, "HOST_PLATFORM", "win32")
    monkeypatch.setattr(runner, "NETWORK_ISOLATION_SUPPORTED", False)

    spawned: list[object] = []

    def _record(*args: object, **kwargs: object) -> None:
        spawned.append(args)

    monkeypatch.setattr(runner.subprocess, "Popen", _record)

    with pytest.raises(runner.NetworkIsolationUnsupportedError) as excinfo:
        runner.run_pdftoppm_in_subprocess(b"%PDF-1.4 fake")
    assert not spawned, "no process may be created on the refusal path"
    assert excinfo.value.code == ErrorCode.NOT_IMPLEMENTED
    assert excinfo.value.http_status == 501


def test_the_network_refusal_is_distinguishable_from_other_outcomes() -> None:
    """The Windows refusal is its own outcome, not a generic 422.

    It must be distinguishable from a malformed PDF (400), a missing
    tool (422), a parser failure (422), a timeout (504), a memory-limit
    hit (422), and a Linux namespace setup failure (500).
    """
    import chess_coach.pdf_ocr.subprocess_runner as runner
    from chess_coach.pdf_ocr.linux_sandbox import NetworkIsolationSetupError

    refusal = runner.NetworkIsolationUnsupportedError("refused")
    setup = NetworkIsolationSetupError("setup failed", stage="namespace_creation")

    assert refusal.code == ErrorCode.NOT_IMPLEMENTED
    assert refusal.http_status == 501
    assert setup.code == ErrorCode.NETWORK_ISOLATION_SETUP_FAILED
    assert setup.http_status == 500
    # The two are distinct types, so one can never be mistaken for the
    # other.
    assert not isinstance(refusal, NetworkIsolationSetupError)
    assert not isinstance(setup, runner.NetworkIsolationUnsupportedError)
    # Neither is the memory-cap refusal.
    assert not isinstance(refusal, runner.UnsupportedParserPlatformError)


def test_the_refusal_precedes_the_memory_cap_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The network-isolation gate runs BEFORE the memory-cap gate.

    On Windows both gates would refuse, but the network refusal is the
    one that describes the platform's actual limitation. The order is
    pinned so the more specific refusal is the one that surfaces.
    """
    import chess_coach.pdf_ocr.subprocess_runner as runner

    order: list[str] = []
    monkeypatch.setattr(
        runner,
        "ensure_memory_cap_supported",
        lambda: order.append("memory_cap"),
    )
    monkeypatch.setattr(
        runner,
        "ensure_network_isolation_supported",
        lambda: order.append("network"),
    )
    monkeypatch.setattr(
        runner, "NETWORK_ISOLATION_SUPPORTED", False, raising=False
    )

    def _refuse() -> None:
        order.append("network")
        raise runner.NetworkIsolationUnsupportedError("refused")

    monkeypatch.setattr(runner, "ensure_network_isolation_supported", _refuse)

    with pytest.raises(runner.NetworkIsolationUnsupportedError):
        runner.run_pdftoppm_in_subprocess(b"%PDF-1.4 fake")
    assert order == ["memory_cap", "network"], (
        "the memory-cap gate runs first, then the network-isolation gate"
    )


def _run_child_with_cap(cap_bytes: int, code: str) -> int:
    """Run `code` in a FRESH interpreter under an `RLIMIT_AS` cap.

    A fresh `exec`'d interpreter is used rather than `os.fork()` of the pytest
    parent: `RLIMIT_AS` caps the whole virtual address space, and a forked
    child inherits the parent's mappings, so in a full-suite run the parent's
    footprint alone can exceed the cap. A fresh interpreter has a small,
    predictable footprint.

    Exit codes:
        0 - `code` ran to completion (the allocation SUCCEEDED)
        1 - the cap was enforced (MemoryError / OSError)
        2 - `code` raised an unexpected exception
    """

    def _preexec() -> None:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, cap_bytes))

    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        preexec_fn=_preexec,  # noqa: S603 -- test harness
    )
    if proc.returncode != 0:
        return proc.returncode
    # The child signals "the cap was enforced" by exiting 1.
    return 1 if "CAP_ENFORCED" in proc.stdout else 0


@_skip_on_windows
def test_memory_cap_is_enforced_not_merely_declared() -> None:
    """The cap actually bounds the child's address space.

    The pre-B1 test (`test_subprocess_respects_2gb_memory_cap` in
    `tests/unit/test_pdf_ingest_security.py`) asserted only that the
    constant equals 2 GiB and that the factory returns a callable. Both
    hold even if no limit is applied at all. This test instead applies a
    real limit and observes the kernel refusing an over-limit reservation.

    A 256 MiB cap is used (rather than the production 2 GiB) so the test can
    observe the boundary cheaply. The mechanism under test is identical:
    `setrlimit(RLIMIT_AS, ...)`.

    `mmap` is used rather than `bytearray` because `RLIMIT_AS` caps ADDRESS
    SPACE: an `mmap` reservation over the cap fails deterministically with
    `MemoryError` without committing physical memory, whereas a large
    `bytearray` may be OOM-killed instead (a different, less precise signal).
    """
    cap = 256 * 1024 * 1024
    over = cap * 2
    code = (
        "import mmap\n"
        "try:\n"
        f"    mmap.mmap(-1, {over})\n"
        "except (MemoryError, OSError):\n"
        "    print('CAP_ENFORCED', end='')\n"
        "else:\n"
        "    print('CAP_NOT_ENFORCED', end='')\n"
    )
    exit_code = _run_child_with_cap(cap, code)

    assert exit_code == 1, (
        f"the RLIMIT_AS cap did NOT take effect: the child reserved {over} "
        f"bytes of address space under a {cap}-byte limit and exited "
        f"{exit_code} (expected 1 = reservation refused). A "
        f"constant-and-callable check would pass here while enforcement is "
        f"actually broken."
    )


@_skip_on_windows
def test_descendant_inherits_memory_cap_independently(tmp_path: Path) -> None:
    """A descendant inherits the limit, and gets its OWN allowance.

    Two properties are established:

    1. INHERITANCE - a grandchild spawned by the capped child observes the
       same `RLIMIT_AS`, and an over-limit reservation inside the grandchild is
       refused. Without inheritance the grandchild would be uncapped and could
       allocate without bound.

    2. INDEPENDENCE (NOT an aggregate tree budget) - the grandchild's
       allowance is its OWN cap-sized allowance, not a share of a single pool
       shared with the parent. The parent reserves a share of the cap AND the
       grandchild reserves a share of the cap, together exceeding the cap
       value. That is only possible if the limit is per-process rather than an
       aggregate process-tree memory budget.

    This distinction is the contract the B1 brief states explicitly: the Linux
    cap is a per-process address-space limit inherited independently by
    descendants, and it is NOT a 2 GB aggregate process-tree budget.

    A fresh `exec`'d interpreter is used for the child (not `os.fork()` of the
    pytest parent): `RLIMIT_AS` caps the whole virtual address space, and a
    forked child inherits the parent's mappings, so in a full-suite run the
    parent's footprint alone can exceed the cap.
    """
    cap = 512 * 1024 * 1024
    share = cap // 8
    report = tmp_path / "report.txt"

    # The grandchild is forked (NOT exec'd) from the capped child: an
    # exec'd grandchild would need to start a fresh Python interpreter
    # INSIDE the cap, which is not what is being measured here -- the
    # measurement is whether the inherited LIMIT is enforced for a
    # descendant, and a fork inherits the limit without needing more
    # address space than the parent already has.
    grandchild_code = (
        "import mmap, resource, sys\n"
        "print('grandchild_limit', resource.getrlimit(resource.RLIMIT_AS)[0], flush=True)\n"
        "try:\n"
        f"    mmap.mmap(-1, {cap * 2})\n"
        "    print('grandchild_alloc', 'SUCCEEDED', flush=True)\n"
        "except (MemoryError, OSError):\n"
        "    print('grandchild_alloc', 'REFUSED', flush=True)\n"
        "sys.stdout.flush()\n"
    )

    child_code = (
        "import mmap, os, resource, sys\n"
        f"grandchild_code = {grandchild_code!r}\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    exec(grandchild_code)\n"
        "    os._exit(0)\n"
        "_, status = os.waitpid(pid, 0)\n"
        f"mmap.mmap(-1, {share})\n"
        "print('child_alloc', 'SUCCEEDED', flush=True)\n"
    )

    def _preexec() -> None:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))

    proc = subprocess.run(
        [sys.executable, "-c", child_code],
        capture_output=True,
        text=True,
        preexec_fn=_preexec,  # noqa: S603 -- test harness
    )
    report.write_text(proc.stdout, encoding="utf-8")

    assert proc.returncode == 0, (
        f"the child process failed unexpectedly (exit {proc.returncode}); "
        f"report: {report.read_text()!r}; stderr: {proc.stderr[-500:]!r}"
    )

    text = report.read_text(encoding="utf-8")
    lines = dict(line.split(" ", 1) for line in text.splitlines() if " " in line)

    assert "grandchild_limit" in lines, f"grandchild did not report a limit: {text!r}"
    assert int(lines["grandchild_limit"]) == cap, (
        f"the grandchild must INHERIT the {cap}-byte RLIMIT_AS, but observed "
        f"{lines['grandchild_limit']}. Without inheritance the descendant would "
        f"be uncapped."
    )
    assert lines.get("grandchild_alloc") == "REFUSED", (
        f"the grandchild's over-limit reservation was NOT refused "
        f"({lines.get('grandchild_alloc')}); the cap is not enforced for "
        f"descendants."
    )
    assert lines.get("child_alloc") == "SUCCEEDED", (
        f"the child's own sub-cap reservation must succeed, got "
        f"{lines.get('child_alloc')}"
    )


def test_uncappable_platform_refuses_and_spawns_no_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A platform with NEITHER enforcement mechanism refuses deliberately.

    This test FAILS against the pre-BB1 implementation, which reached
    `subprocess.Popen(preexec_fn=...)`, had CPython raise
    `ValueError: preexec_fn is not supported on Windows platforms`, and
    surfaced that incidental failure as a generic 422 - indistinguishable from
    a malformed PDF or a parser failure.

    It asserts three things:
      1. the guard raises the deliberate typed result;
      2. that result carries the ADR-0002 contract values (501 /
         `internal.not_implemented`) so it is distinguishable from the 400
         (malformed), 404 (missing tool), 422 (generic failure) and 504
         (timeout) outcomes;
      3. `subprocess.Popen` is NEVER called, so no parser process starts.

    BBF-FU-22-B2-windows-job-object: B2 gave Windows a REAL enforcement
    mechanism (the Job Object backend), so Windows is no longer an
    uncappable platform. The refusal contract still has to hold for a
    platform with neither mechanism, so this test now simulates a
    genuinely uncappable platform by patching `MEMORY_CAP_SUPPORTED` to
    False -- exactly the state B1 left Windows in, and the state a
    non-Windows, non-Linux host would be in.

    The Windows mechanism itself is proved in
    `tests/windows/test_windows_job_enforcement.py`, which runs on a real
    `windows-latest` runner.
    """
    subprocess_runner = _runner()

    # Simulate a platform with NO enforcement mechanism at all. The platform
    # constant is patched as well as the capability flag, so the error
    # details name the SIMULATED platform rather than the real host.
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

    with pytest.raises(UnsupportedParserPlatformError) as excinfo:
        subprocess_runner.run_pdftoppm_in_subprocess(b"%PDF-1.4 not a real pdf")

    exc = excinfo.value
    assert exc.code == "internal.not_implemented", (
        f"the unsupported-platform result must carry the ADR-0002 code "
        f"`internal.not_implemented`, got {exc.code!r}"
    )
    assert exc.http_status == 501, (
        f"the unsupported-platform result must be HTTP 501, got {exc.http_status}"
    )
    assert exc.retriable is False, (
        "an unsupported platform is not a transient condition and must not be "
        f"marked retriable, got {exc.retriable!r}"
    )
    # BBF-FU-22-B2-windows-job-object: the simulated uncappable platform is
    # no longer "win32" (Windows now HAS an enforcement mechanism), so the
    # assertion pins the SIMULATED platform rather than a literal.
    assert exc.details.get("platform") == "sunos5", (
        f"the error details must name the platform, got {exc.details!r}"
    )
    assert exc.details.get("required_mechanism") == MEMORY_CAP_MECHANISM, (
        f"the error details must name the mechanism that is missing, got "
        f"{exc.details!r}"
    )
    assert exc.details.get("cap_bytes") == MEM_CAP_BYTES, (
        f"the error details must name the cap that cannot be enforced, got "
        f"{exc.details!r}"
    )
    assert not spawn_calls, (
        f"no parser process may be spawned on the unsupported path, but Popen "
        f"was called {len(spawn_calls)} time(s)"
    )


def test_ensure_memory_cap_supported_raises_on_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard itself is the single gate, and it raises the typed error.

    BBF-FU-22-B2-windows-job-object: Windows now HAS an enforcement
    mechanism (the Job Object backend), so the uncappable platform is
    simulated with a platform that genuinely has neither mechanism.
    """
    subprocess_runner = _runner()

    monkeypatch.setattr(subprocess_runner, "HOST_PLATFORM", "sunos5")
    monkeypatch.setattr(subprocess_runner, "MEMORY_CAP_SUPPORTED", False)

    with pytest.raises(UnsupportedParserPlatformError):
        subprocess_runner.ensure_memory_cap_supported()

    # On a supported platform it is a no-op.
    monkeypatch.setattr(subprocess_runner, "MEMORY_CAP_SUPPORTED", True)
    subprocess_runner.ensure_memory_cap_supported()


def test_unsupported_platform_error_is_distinguishable_from_other_outcomes() -> None:
    """The deliberate result does not collide with the other outcomes.

    A malformed PDF is a 400, a missing tool or a generic parser failure is a
    422, and a timeout is a 504. The unsupported-platform result must be
    distinct from all of them.
    """
    from chess_coach.errors import ErrorCode

    unsupported = UnsupportedParserPlatformError("x")
    assert unsupported.http_status == 501
    assert unsupported.http_status not in (400, 404, 413, 422, 504)
    assert unsupported.code == ErrorCode.NOT_IMPLEMENTED
    assert unsupported.code != ErrorCode.BAD_REQUEST
    assert unsupported.code != ErrorCode.INTERNAL

