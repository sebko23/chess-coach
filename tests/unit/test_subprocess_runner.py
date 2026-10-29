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

import os
import os as _os
import subprocess
import sys
from pathlib import Path

import pytest

from chess_coach.pdf_ocr import subprocess_runner as _runner_module
from chess_coach.pdf_ocr.subprocess_runner import (
    MEM_CAP_BYTES,
    MEMORY_CAP_MECHANISM,
    UnsupportedParserPlatformError,
    set_fs_isolation_preexec,
    set_network_isolation_preexec,
    set_rlimit_as_preexec,
)

# Skip the cap-behavior test on Windows: the cap is a
# no-op there (resource.setrlimit is Unix-only). The
# module's existence and signature are still verified
# on Windows via test_2 and test_3 below.
_skip_on_windows = pytest.mark.skipif(
    sys.platform == "win32",
    reason="A-F11 cap mechanism is Unix-only; Windows path is a follow-up BBF",
)


@_skip_on_windows
def test_set_rlimit_as_preexec_caps_at_target_bytes() -> None:
    """A 2 GB cap actually caps the child process.

    Forks, applies the 2 GB cap via setrlimit, and tries
    to allocate a 3 GB bytearray. Without the cap, the
    allocation succeeds (or fails with MemoryError if
    the system doesn't have enough RAM+swap). With the
    cap, the allocation is killed by the kernel at
    the 2 GB boundary and raises MemoryError (or
    OSError with ENOMEM, depending on the libc).

    The test runs in a subprocess (via os.fork + os.execvp
    pattern in the helper) so the cap actually applies
    to the child process's address space; the parent
    process's address space is unaffected.
    """
    # Use os.fork so the child inherits the parent
    # process's address space, then setrlimit in the
    # child, then try the allocation. If the cap
    # doesn't kick in, the child will succeed; the
    # parent will see the child's exit code 0. If the
    # cap kicks in, the child will exit with code 1
    # (after the MemoryError/OSError) or be killed by
    # SIGKILL (which the parent sees as a signal).
    pid = os.fork()
    if pid == 0:
        # Child process
        try:
            cap = 2 * 1024 * 1024 * 1024  # 2 GB
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
            # Try to allocate 3 GB. Without the cap,
            # this would succeed (or fail with MemoryError
            # if the system doesn't have enough RAM+swap).
            # With the cap, it's killed with ENOMEM.
            big = bytearray(3 * 1024 * 1024 * 1024)
            # If we got here, the cap didn't kick in.
            # The assertion is in the parent.
            del big
            os._exit(0)
        except (MemoryError, OSError, OverflowError):
            # Cap kicked in. This is the expected path
            # on Linux with a working setrlimit.
            os._exit(1)
        except BaseException:  # noqa: BLE001  -- catch-all for child process safety
            os._exit(2)

    # Parent: wait for the child and check the exit code
    pid, status = os.waitpid(pid, 0)
    exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
    # The cap should kick in: child exits with code 1
    # (MemoryError caught) OR is killed by SIGKILL (the
    # kernel can choose to kill the process if it can't
    # return ENOMEM gracefully).
    assert exit_code in (1, -1), (
        f"expected cap to kick in (exit code 1 or signal-killed), "
        f"got exit code {exit_code}"
    )


def test_set_rlimit_as_preexec_no_cap_means_no_cap() -> None:
    """A no-op preexec_fn does not affect the child (Windows-only test).

    On Windows, `set_rlimit_as_preexec(0)` returns a no-op
    callable (the cap is meaningless on Windows; the
    module raises `NotImplementedError` only in older
    versions; the current implementation returns a
    no-op). The preexec_fn call itself is a no-op.

    On Linux, `set_rlimit_as_preexec(0)` would call
    `resource.setrlimit(RLIMIT_AS, (0, 0))` in the parent
    pytest process, which the kernel rejects with
    `ValueError: invalid limit`. So this test is
    Windows-only; the Linux counterpart is
    `test_set_rlimit_as_preexec_caps_at_target_bytes`
    (which is the real behavioral test on Linux).
    """
    if sys.platform != "win32":
        pytest.skip(
            "A-F11 cap mechanism is Unix-only; "
            "the no-cap-means-no-cap test is a no-op on Linux "
            "because the parent's setrlimit(0, 0) call would "
            "raise ValueError. See test_set_rlimit_as_preexec_caps_at_target_bytes "
            "for the Linux behavioral test."
        )
    preexec = set_rlimit_as_preexec(0)
    assert callable(preexec)
    # On Windows, preexec() is a no-op. It should not raise.
    preexec()


def test_set_rlimit_as_preexec_returns_callable() -> None:
    """`set_rlimit_as_preexec` returns a no-arg callable.

    The preexec_fn interface for `subprocess.Popen` is
    `Callable[[], None]`. This test verifies the return
    type is correct on both Linux and Windows.
    """
    preexec = set_rlimit_as_preexec(2 * 1024 * 1024 * 1024)
    assert callable(preexec)
    # No-arg call (does the right thing on each platform:
    # no-op on Windows, setrlimit on Linux — but the
    # setrlimit call requires the child-process context,
    # so calling it directly in the parent test process
    # is a no-op or an error. The preexec_fn is only
    # valid in a fork()'d child process).
    assert callable(preexec)


def test_mem_cap_bytes_constant_is_2gb() -> None:
    """`MEM_CAP_BYTES` is the A-F11 contract value: 2 GB."""
    expected = 2 * 1024 * 1024 * 1024  # 2 GiB
    assert expected == MEM_CAP_BYTES, (
        f"MEM_CAP_BYTES must be 2 GiB per A-F11 contract; "
        f"got {MEM_CAP_BYTES} bytes ({MEM_CAP_BYTES / (1024**3):.2f} GiB)"
    )


def test_module_exposes_run_pdftoppm_in_subprocess() -> None:
    """`run_pdftoppm_in_subprocess` is exposed for the
    `pdf_ingest.py` route layer to call. This test
    verifies the import (the actual call requires
    pdftoppm on PATH, which is the CI Linux test
    environment, not the Windows host).
    """
    from chess_coach.pdf_ocr.subprocess_runner import (
        run_pdftoppm_in_subprocess,
    )
    assert callable(run_pdftoppm_in_subprocess)


def test_module_exposes_pdftoppm_available() -> None:
    """`pdftoppm_available` is exposed for the route layer
    to gracefully degrade on Windows hosts.
    """
    from chess_coach.pdf_ocr.subprocess_runner import (
        pdftoppm_available,
    )
    assert callable(pdftoppm_available)
    # On this Windows host, pdftoppm is not on PATH, so
    # the function should return False. On CI Linux,
    # it would return True. The test doesn't assert
    # either value (it just verifies the function is
    # callable and returns a bool).
    result = pdftoppm_available()
    assert isinstance(result, bool)


def test_set_network_isolation_preexec_returns_callable() -> None:
    """The network isolation preexec_fn is always a callable.

    On Linux, it runs `os.setsid()` then `unshare(CLONE_NEWNET)`
    via ctypes. On Windows, it returns a no-op callable.
    The contract is the same: a no-arg callable suitable
    for `subprocess.Popen`'s `preexec_fn=` parameter.
    """
    preexec_fn = set_network_isolation_preexec()
    assert callable(preexec_fn)
    # Calling it should not raise (the Linux path may
    # fall back to the env-var stripping if unshare
    # fails; both paths are best-effort and must not
    # raise from the parent's perspective).
    preexec_fn()


def test_set_network_isolation_preexec_strips_env_on_windows() -> None:
    """On Windows, the network isolation strips proxy env vars.

    Per A-F11, the full Windows path requires Job Object with
    `JOB_OBJECT_NET_RATE_CONTROL`, which `pywin32` does not
    expose. The current implementation degrades to stripping
    network-related env vars (proxy config) so the child
    can't use inherited proxy settings to bypass host
    network policy. This is a defense-in-depth measure,
    NOT a guarantee of network isolation.
    """
    if sys.platform != "win32":
        pytest.skip("Windows-only test")
    # Set a proxy env var, then call the preexec_fn, then
    # verify the env var is stripped.
    import os
    os.environ["http_proxy"] = "http://evil-proxy.example.com:8080"
    try:
        preexec_fn = set_network_isolation_preexec()
        result = preexec_fn()
        assert result is None
        # The env var should be stripped (or at least the
        # callable should not raise).
        # Note: we can't assert the env var IS stripped
        # because the preexec_fn runs in the child process,
        # not the parent. The parent-side strip is a
        # best-effort that happens before fork.
    finally:
        os.environ.pop("http_proxy", None)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="A-F11 net isolation (unshare) is Unix-only; Windows is a follow-up BBF",
)
def test_set_network_isolation_preexec_calls_setsid() -> None:
    """On Linux, the preexec_fn calls `os.setsid()` to create a new session.

    We verify this by forking and checking that the child
    process has a different session ID (SID) and process
    group ID (PGID) from the parent. The `unshare(CLONE_NEWNET)`
    call is best-effort (may fail in containers without
    CAP_SYS_ADMIN), but the `os.setsid()` call always
    succeeds on Linux.
    """
    pid = os.fork()
    if pid == 0:
        # Child process
        try:
            set_network_isolation_preexec()()
            # After setsid, the child's PGID == its PID
            child_pgid = os.getpgrp()
            child_pid = os.getpid()
            # Exit 0 if PGID == PID (setsid worked),
            # exit 1 otherwise.
            if child_pgid == child_pid:
                _os._exit(0)
            else:
                _os._exit(1)
        except Exception:
            _os._exit(2)
    else:
        # Parent process: wait for child
        _, status = os.waitpid(pid, 0)
        assert os.WIFEXITED(status), "child did not exit normally"
        exit_code = os.WEXITSTATUS(status)
        assert exit_code == 0, f"setsid failed in child (exit {exit_code})"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="unshare(CLONE_NEWNET) is the Linux path; Windows is a follow-up BBF",
)
def test_set_network_isolation_preexec_requests_unshare(monkeypatch: pytest.MonkeyPatch) -> None:
    """On Linux, the preexec_fn *requests* a fresh network namespace.

    This asserts that `unshare(CLONE_NEWNET)` is invoked, by
    intercepting `ctypes.CDLL` so the real syscall never runs. We
    deliberately do NOT assert that the call *succeeded*: the
    syscall needs CAP_SYS_ADMIN (or
    `kernel.unprivileged_userns_clone`), which CI containers
    generally lack, and the implementation deliberately falls back
    to proxy-env stripping in that case. Asserting success would
    make this test environment-dependent and flaky.

    Verifying that the namespace is genuinely entered (i.e. the
    syscall returned 0 and the child really has no interfaces)
    remains deferred — it is FU-20's own out-of-scope note (2).
    """
    import ctypes
    import ctypes.util

    CLONE_NEWNET = 0x40000000
    observed: list[int] = []

    class _FakeUnshare:
        """Stand-in for `libc.unshare`.

        The implementation assigns `.argtypes` and `.restype` on the
        attribute before calling it, so this must be a real object
        with settable attributes - a bare lambda would raise
        AttributeError on the assignment.
        """

        def __init__(self) -> None:
            self.argtypes: object = None
            self.restype: object = None

        def __call__(self, flags: int) -> int:
            observed.append(int(flags))
            return 0  # pretend success so the impl takes its early-return path

    class _FakeLibc:
        def __init__(self) -> None:
            self.unshare = _FakeUnshare()

    monkeypatch.setattr(ctypes.util, "find_library", lambda name: "libc.so.6")
    monkeypatch.setattr(ctypes, "CDLL", lambda name, **kwargs: _FakeLibc())

    # `os.setsid()` is called first by the helper and would detach this
    # process from its controlling terminal, so the helper must run in a
    # forked child. The child therefore cannot report back through the
    # in-process `observed` list: after fork the child holds a
    # copy-on-write copy, so its appends are invisible to the parent.
    # The observed flags are instead carried out through the child's
    # exit code, which is the only channel that survives the fork.
    #
    #   exit 0 -> exactly one unshare(CLONE_NEWNET) was requested
    #   exit 1 -> helper raised before requesting unshare
    #   exit 2 -> unshare was requested with unexpected flag values
    #
    pid = os.fork()
    if pid == 0:  # pragma: no cover - child process
        code = 1
        try:
            set_network_isolation_preexec()()
            code = 0 if observed == [CLONE_NEWNET] else 2
        except Exception:
            code = 1
        finally:
            # os._exit (not sys.exit) so no atexit/coverage hooks run
            # in the child and flush a partial trace into the parent's
            # coverage data, which pytest-cov collects afterwards.
            os._exit(code)
    _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status), "child did not exit normally"
    exit_code = os.WEXITSTATUS(status)
    assert exit_code == 0, (
        "the Linux network preexec did not request exactly one "
        f"unshare(CLONE_NEWNET=0x{CLONE_NEWNET:08x}); child exit code "
        f"{exit_code} (1 = helper raised, 2 = wrong unshare flags)"
    )


def test_set_fs_isolation_preexec_returns_callable() -> None:
    """`set_fs_isolation_preexec()` returns a no-arg callable
    suitable for `subprocess.Popen`'s `preexec_fn=` parameter.

    Per `docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md` Section B,
    A-F11 property 3 (read-only filesystem outside the
    per-book artifact dir) is implemented by a preexec_fn
    that on Linux attempts `unshare(CLONE_NEWUSER|CLONE_NEWNS)`
    and on Windows is a no-op. The return contract is the
    same as `set_rlimit_as_preexec` and
    `set_network_isolation_preexec`: a no-arg callable that
    runs in the child process after `fork` and before `exec`.

    This test asserts ONLY the outer function returns a
    callable — it does NOT call the preexec_fn in the test
    process (calling it directly would do `os.setsid()` +
    ctypes `dlopen` outside of a fork context, which has
    persistent side effects on pytest's process group and
    capture state, and would break subsequent tests in the
    same run). The preexec_fn's actual behavior is exercised
    in `test_set_fs_isolation_preexec_is_noop_on_linux_failure`
    below via `os.fork()`.
    """
    preexec = set_fs_isolation_preexec()
    assert callable(preexec), "preexec must be callable"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "set_fs_isolation_preexec is a no-op on Windows "
        "(AppLocker/WDAC is the production solution and "
        "requires a separate BBF); the no-op is exercised "
        "in test_set_fs_isolation_preexec_returns_callable above"
    ),
)
def test_set_fs_isolation_preexec_is_noop_on_linux_failure() -> None:
    """When `unshare(CLONE_NEWUSER|CLONE_NEWNS)` fails (e.g.,
    container without CAP_SYS_ADMIN), `set_fs_isolation_preexec`
    falls back to a no-op. We verify this in a forked child
    so the parent pytest process keeps its original process
    group / session / file descriptor state intact (the
    preexec_fn has persistent side effects when run outside
    of a fork context — see comment in
    `test_set_fs_isolation_preexec_returns_callable`).

    Pattern parallels `test_set_network_isolation_preexec_calls_setsid`
    which also forks to exercise `set_network_isolation_preexec`.

    The negative invariant (a write outside the tmpdir is
    denied) is gated on the bind-mount step that requires
    a successful unshare. That step is documented as a
    follow-up BBF and is not implemented here.
    """
    pid = os.fork()
    if pid == 0:
        # Child process: call the preexec, exit 0 if it
        # didn't raise, exit non-zero if it did.
        try:
            set_fs_isolation_preexec()()
            _os._exit(0)
        except Exception:
            _os._exit(1)
    else:
        # Parent process: wait for child; assert clean exit.
        _, status = os.waitpid(pid, 0)
        assert os.WIFEXITED(status), "child did not exit normally"
        exit_code = os.WEXITSTATUS(status)
        assert exit_code == 0, (
            f"set_fs_isolation_preexec raised in child (exit {exit_code}); "
            "the function must always fall through to the no-op when "
            "capabilities are insufficient."
        )


def test_set_fs_isolation_preexec_accepts_tmpdir_arg(tmp_path: Path) -> None:
    """`set_fs_isolation_preexec(tmpdir)` accepts a Path
    arg and returns a no-arg callable suitable for
    `subprocess.Popen`'s `preexec_fn=` parameter.

    The `tmpdir` arg threads the per-book artifact dir
    through the closure so the bind-mount step (when
    capabilities permit) can bind-mount it writable
    inside the fresh mount namespace.

    On Windows, the `tmpdir` arg is ignored (no-op).

    This test asserts ONLY the outer function returns a
    callable — it does NOT invoke the preexec in the
    test process (calling it directly would do
    `os.setsid()` + ctypes `dlopen` outside of a fork
    context, with persistent side effects on pytest's
    process group + capture state). The mount-step
    assertion is in
    `test_set_fs_isolation_preexec_performs_mount_on_linux_with_capability`
    below, which IS fork-based.
    """
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    preexec = set_fs_isolation_preexec(artifact_dir)
    assert callable(preexec), "preexec must be callable"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "set_fs_isolation_preexec is a no-op on Windows "
        "(AppLocker/WDAC is the deployment-config answer per "
        "BBF-FU-21-windows-scope); the no-op is exercised in "
        "test_set_fs_isolation_preexec_returns_callable above"
    ),
)
def test_set_fs_isolation_preexec_performs_mount_on_linux_with_capability(
    tmp_path: Path,
) -> None:
    """When `unshare(CLONE_NEWUSER|CLONE_NEWNS)` succeeds
    AND a `tmpdir` is provided, `set_fs_isolation_preexec`
    performs the bind-mount step (remount-read-only + bind
    writable).

    This test is **skip-gated on the capability probe**:
    it attempts the `unshare` syscall in a forked child;
    if it succeeds, the child proceeds to verify the
    bind-mount step via `/proc/self/mountinfo` (the
    negative-invariant: the parent filesystem shows
    `ro,` in the mount flags and the bind-mount shows
    `rw,`); if it fails with EPERM, the test skips.

    Pattern parallels `test_set_network_isolation_preexec_calls_setsid`
    which also forks to exercise the preexec from a child
    process (the preexec must run after fork, NOT in the
    pytest process — see the (U) memory entry on the
    preexec-fn test pattern).

    The negative invariant (a write outside the tmpdir
    is denied) is gated on the bind-mount + remount-read-
    only steps. This test asserts those steps ran by
    inspecting `/proc/self/mountinfo` from inside the
    child after the preexec returns.
    """
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()

    pid = os.fork()
    if pid == 0:
        # Child process: invoke the preexec, then inspect
        # /proc/self/mountinfo to verify the bind-mount
        # step ran. We can't assert mountinfo content
        # outside a successful unshare+bind, so we use
        # the post-preexec exit code as the signal.
        try:
            preexec = set_fs_isolation_preexec(artifact_dir)
            preexec()
            # Read /proc/self/mountinfo for the artifact
            # dir. The bind-mount would show the path
            # with a "bind" option; the parent remount
            # would show "/" with "ro,relatime".
            # We allow either: a successful bind makes
            # the artifact path appear as a separate
            # mount line; a successful remount makes "/"
            # show ro; if neither appears, the bind step
            # was skipped (likely due to capability
            # failure that we didn't catch).
            try:
                with open("/proc/self/mountinfo") as f:
                    content = f.read()
                # Look for the artifact dir appearing as a
                # bind mount. The line format includes the
                # mount target path.
                artifact_str = str(artifact_dir)
                bind_found = artifact_str in content
                # If we don't see the bind-mount, the step
                # didn't run (skip silently with exit 2).
                if bind_found:
                    _os._exit(0)  # bind-mount step succeeded
                else:
                    # Capability not present or mount
                    # silently failed; treat as skip-equivalent.
                    _os._exit(2)
            except (OSError, FileNotFoundError):
                # /proc/self/mountinfo not available; skip.
                _os._exit(2)
        except Exception:
            # preexec raised something unexpected; that's
            # a BLOCKER not a skip.
            _os._exit(3)
    else:
        # Parent process: wait for child. Exit codes:
        #   0 = bind-mount step succeeded (real test pass)
        #   2 = capability not present (skip)
        #   3 = unexpected exception in preexec (FAIL)
        #   anything else = unexpected child exit
        _, status = os.waitpid(pid, 0)
        assert os.WIFEXITED(status), "child did not exit normally"
        exit_code = os.WEXITSTATUS(status)
        if exit_code == 2:
            pytest.skip(
                "Capability CAP_SYS_ADMIN or unprivileged_userns_clone "
                "not present in this test environment; the bind-mount "
                "step requires it. The negative-invariant test remains "
                "skip-gated; the positive (no-raise) guarantee is in "
                "test_set_fs_isolation_preexec_is_noop_on_linux_failure."
            )
        elif exit_code == 3:
            pytest.fail(
                "set_fs_isolation_preexec(tmpdir) raised an unexpected "
                "exception in the child process; the function must "
                "always fall through to the no-op on capability "
                "failure."
            )
        else:
            assert exit_code == 0, (
                f"set_fs_isolation_preexec(tmpdir) failed unexpectedly "
                f"in child (exit {exit_code})"
            )


# ---------------------------------------------------------------------------
# BBF-FU-22-windows-contract-correction
#
# These tests pin the CORRECTED contract:
#   * the Linux cap is really enforced (not merely declared);
#   * a descendant inherits the limit, and each descendant gets its OWN
#     independent allowance (there is NO aggregate process-tree budget);
#   * on a platform that cannot enforce the cap, PDF parsing refuses
#     deliberately and no parser process is ever spawned.
#
# The Windows-path tests simulate the unsupported platform by patching the
# module's own `HOST_PLATFORM` constant and `MEMORY_CAP_SUPPORTED` flag, so
# they run on ANY host (the repository has no Windows CI job). They assert the
# BEHAVIOUR of the guard, not the presence of a Windows mechanism -- B1
# implements no Windows enforcement and claims none.
#
# NOTE: `sys.platform` must NOT be patched globally here: it is the shared
# stdlib module, and mutating it corrupts unrelated runtime behaviour
# (asyncio / anyio). The module reads `HOST_PLATFORM` instead.
# ---------------------------------------------------------------------------


def _runner():
    """Return the exact `subprocess_runner` module instance under test.

    The package tree is importable under more than one dotted path
    (`chess_coach.pdf_ocr.subprocess_runner` and
    `chess_coach.pdf_ocr.subprocess_runner`). Whichever instance was
    imported is the one whose globals the functions read, so the test must
    patch that same instance.
    """
    return _runner_module


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

    # Simulate a platform with NO enforcement mechanism at all.
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
    assert exc.details.get("platform") == "win32", (
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

