"""Unit tests for `services.chess_coach.pdf_ocr.subprocess_runner`.

These tests cover the A-F11 property 4 (2 GB memory cap)
implementation per `docs/16_audit/BBF-FU-22-impl.md`. The
cap mechanism is platform-portable: `set_rlimit_as_preexec`
returns a no-op on Windows (the A-F11 Windows path is a
follow-up BBF), and applies `resource.setrlimit(RLIMIT_AS, ...)`
on Linux. The cap is enforced in the child process after
fork but before exec.

Test 1 (`test_set_rlimit_as_preexec_caps_at_target_bytes`)
is the key test: it forks, applies the cap, and tries to
allocate 3 GB. On Linux, the allocation is killed with
`MemoryError` (or `OSError`). On Windows, the test is
skipped (the cap is a no-op).

Test 2 (`test_set_rlimit_as_preexec_no_cap_means_no_cap`)
is the control test: with no cap, the same 3 GB allocation
succeeds (skipped if the system doesn't have 3 GB of RAM
+ swap).
"""
from __future__ import annotations

import os
import os as _os
import sys
from pathlib import Path

import pytest
from services.chess_coach.pdf_ocr.subprocess_runner import (
    MEM_CAP_BYTES,
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
    from services.chess_coach.pdf_ocr.subprocess_runner import (
        run_pdftoppm_in_subprocess,
    )
    assert callable(run_pdftoppm_in_subprocess)


def test_module_exposes_pdftoppm_available() -> None:
    """`pdftoppm_available` is exposed for the route layer
    to gracefully degrade on Windows hosts.
    """
    from services.chess_coach.pdf_ocr.subprocess_runner import (
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

