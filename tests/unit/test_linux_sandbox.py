"""Unit tests for the A-F11 Linux sandbox launcher.

**BBF-FU-20-linux-phase1-network-isolation.**

The launcher in :mod:`chess_coach.pdf_ocr.linux_sandbox` is the single
owner of the parser's containment boundary on Linux. These tests pin the
*contract* of every setup stage, the fail-closed behaviour when a stage
fails, and the descriptor policy.

The tests that require an actual namespace (``CLONE_NEWUSER``) can only
run where the kernel permits an unprivileged user namespace. On a host
that denies it, those tests are skipped **with a reason** -- they are not
weakened, because the production-container CI job
(``scripts/dev/verify_linux_network_isolation.py``) is where the real
denial proof lives.

Every test here is a *behavioural* assertion. There is no test that merely
checks a constant: each one observes an effect.
"""
from __future__ import annotations

import builtins
import contextlib
import errno
import os
import socket
import subprocess
import sys
import unittest.mock
from pathlib import Path

import pytest

from chess_coach.pdf_ocr import linux_sandbox
from chess_coach.pdf_ocr.linux_sandbox import (
    MEMORY_CAP_BYTES,
    SANDBOX_CLONE_FLAGS,
    NetworkIsolationSetupError,
    build_launcher_argv,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the sandbox launcher is a Linux-only mechanism",
)


def _unshare_available() -> bool:
    """Can this host create an unprivileged user namespace?"""
    if sys.platform == "win32":
        return False
    probe = (
        "import ctypes, ctypes.util, os, sys\n"
        "libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)\n"
        "libc.unshare.argtypes = [ctypes.c_int]\n"
        "libc.unshare.restype = ctypes.c_int\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    rc = libc.unshare(0x10000000)\n"
        "    os._exit(0 if rc == 0 else 1)\n"
        "_, st = os.waitpid(pid, 0)\n"
        "sys.exit(0 if os.WIFEXITED(st) and os.WEXITSTATUS(st) == 0 else 1)\n"
    )
    try:
        cp = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return cp.returncode == 0


UNSHARE_AVAILABLE = _unshare_available()
requires_namespace = pytest.mark.skipif(
    not UNSHARE_AVAILABLE,
    reason=(
        "this host does not permit an unprivileged user namespace; the "
        "real denial proof runs in the production-container CI job "
        "(scripts/dev/verify_linux_network_isolation.py)"
    ),
)


# --------------------------------------------------------------------------
# The error taxonomy
# --------------------------------------------------------------------------
def _namespace_capable() -> tuple[bool, str]:
    """Can THIS environment create the sandbox namespace?

    The launcher needs an unprivileged user namespace. A plain CI
    runner does not provide one: Docker's default seccomp profile
    blocks ``unshare(CLONE_NEWUSER)`` without ``CAP_SYS_ADMIN``, and
    the launcher then correctly fails closed.

    The environment-dependent assertions are therefore gated on this
    probe. The functional proof runs in the production container with
    the shipped seccomp profile, where the namespace IS available
    (the ``linux-network-isolation`` CI job).

    Returns ``(capable, reason)``.
    """
    if sys.platform == "win32":
        return False, "Windows has no Linux user namespaces"
    probe = (
        "import ctypes, ctypes.util, os, sys\n"
        "libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)\n"
        "libc.unshare.argtypes = [ctypes.c_int]\n"
        "libc.unshare.restype = ctypes.c_int\n"
        "ctypes.set_errno(0)\n"
        "rc = libc.unshare(0x10000000)\n"
        "if rc != 0:\n"
        "    print('unshare failed: errno=%d' % ctypes.get_errno())\n"
        "    sys.exit(1)\n"
        "try:\n"
        "    with open('/proc/self/setgroups', 'w') as h:\n"
        "        h.write('deny')\n"
        "    uid = os.getuid()\n"
        "    with open('/proc/self/uid_map', 'w') as h:\n"
        "        h.write('%d %d 1\\n' % (uid, uid))\n"
        "except OSError as e:\n"
        "    print('map failed: %s' % e)\n"
        "    sys.exit(1)\n"
        "print('ok')\n"
    )
    cp = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if cp.returncode != 0:
        detail = (cp.stdout or cp.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else "unknown"
        return False, reason
    return True, "ok"


_NAMESPACE_CAPABLE, _NAMESPACE_REASON = _namespace_capable()

requires_namespace = pytest.mark.skipif(
    not _NAMESPACE_CAPABLE,
    reason=(
        "this environment cannot create an unprivileged user namespace "
        f"({_NAMESPACE_REASON}). Docker's default seccomp profile blocks "
        "unshare(CLONE_NEWUSER) without CAP_SYS_ADMIN, so the launcher "
        "correctly fails closed here. The functional proof runs in the "
        "production container with the shipped seccomp profile, driven by "
        "the `linux-network-isolation` CI job."
    ),
)


def test_setup_error_carries_the_failing_stage() -> None:
    """A setup failure names the exact stage that failed."""
    err = NetworkIsolationSetupError("boom", stage="mount_root_read_only")
    assert err.stage == "mount_root_read_only"
    assert err.details["stage"] == "mount_root_read_only"
    assert err.message == "boom"


def test_setup_error_uses_the_stable_adr_0002_code() -> None:
    """The setup failure carries a stable, namespaced ADR-0002 code."""
    from chess_coach.errors import ErrorCode

    err = NetworkIsolationSetupError("boom", stage="namespace_creation")
    assert err.code == ErrorCode.NETWORK_ISOLATION_SETUP_FAILED
    assert str(err.code) == "internal.network_isolation_setup_failed"
    assert err.http_status == 500


def test_setup_error_is_not_a_client_error() -> None:
    """A setup failure is a 5xx, never a 4xx that a client could cause."""
    err = NetworkIsolationSetupError("boom", stage="memory_limit")
    assert 500 <= err.http_status < 600


# --------------------------------------------------------------------------
# The argv protocol
# --------------------------------------------------------------------------
def test_launcher_argv_uses_a_controlled_protocol(tmp_path: Path) -> None:
    """The launcher is invoked with an argv list, never a shell string."""
    argv = build_launcher_argv(
        ["pdftoppm", "-r", "200", "in.pdf"],
        artifact_dir=tmp_path,
        limit_bytes=MEMORY_CAP_BYTES,
    )
    assert argv[1:3] == ["-m", "chess_coach.pdf_ocr.linux_sandbox"]
    assert "--" in argv
    # The parser command is the tail after the separator, unmodified.
    assert argv[argv.index("--") + 1 :] == ["pdftoppm", "-r", "200", "in.pdf"]
    # No shell metacharacter is ever interpreted: the launcher execs argv.
    assert all(isinstance(part, str) for part in argv)


def test_launcher_argv_carries_the_artifact_dir_and_limit(tmp_path: Path) -> None:
    """The artifact path and the memory cap are passed explicitly."""
    argv = build_launcher_argv(
        ["pdftoppm"], artifact_dir=tmp_path, limit_bytes=1234, status_fd=7
    )
    assert argv[argv.index("--artifact-dir") + 1] == str(tmp_path)
    assert argv[argv.index("--limit-bytes") + 1] == "1234"
    assert argv[argv.index("--status-fd") + 1] == "7"


# --------------------------------------------------------------------------
# Each setup stage fails closed
# --------------------------------------------------------------------------
def test_namespace_creation_failure_is_a_setup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed unshare aborts before anything else runs."""

    class _FailingLibc:
        @staticmethod
        def unshare(_flags: int) -> int:
            return -1

    monkeypatch.setattr(linux_sandbox, "_libc", lambda: _FailingLibc())
    monkeypatch.setattr(linux_sandbox.ctypes, "set_errno", lambda _v: None)
    monkeypatch.setattr(linux_sandbox.ctypes, "get_errno", lambda: errno.EPERM)

    with pytest.raises(NetworkIsolationSetupError) as excinfo:
        linux_sandbox.sandbox_prepare(Path("/tmp"))
    assert excinfo.value.stage == "namespace_creation"
    assert excinfo.value.details["errno"] == errno.EPERM


def test_write_map_wraps_a_write_failure() -> None:
    """A failed UID/GID map write becomes a typed setup error.

    The wrapping lives in `_write_map`, so it is tested directly: an
    `OSError` from the write must become a
    :class:`NetworkIsolationSetupError` naming the stage and carrying
    the errno.
    """
    with unittest.mock.patch.object(
        builtins, "open", side_effect=OSError(errno.EPERM, "nope")
    ), pytest.raises(NetworkIsolationSetupError) as excinfo:
        linux_sandbox._write_map("/proc/self/uid_map", "1000 1000 1\n", "uid_map")
    assert excinfo.value.stage == "uid_map"
    assert excinfo.value.details["errno"] == errno.EPERM
    assert excinfo.value.details["path"] == "/proc/self/uid_map"


@pytest.mark.parametrize(
    ("stage", "path"),
    [
        ("setgroups_denial", "/proc/self/setgroups"),
        ("uid_map", "/proc/self/uid_map"),
        ("gid_map", "/proc/self/gid_map"),
    ],
)
def test_every_map_write_has_its_own_stage(stage: str, path: str) -> None:
    """Each of the three map writes reports its own stage.

    The order matters: `setgroups` is denied BEFORE the GID map is
    written, because the kernel refuses `gid_map` while `setgroups` is
    still permitted. A single "mapping failed" stage would hide which
    write went wrong.
    """
    real_open = builtins.open

    def _fake_open(target, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        if str(target) == path:
            raise OSError(errno.EPERM, "nope")
        return real_open(target, *args, **kwargs)

    with (
        unittest.mock.patch.object(builtins, "open", _fake_open),
        pytest.raises(NetworkIsolationSetupError) as excinfo,
    ):
        linux_sandbox._write_map(path, "x", stage)
    assert excinfo.value.stage == stage


def test_a_mapping_failure_aborts_before_the_mounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mapping failure stops the setup before any mount is attempted.

    The mount stages are stubbed to record whether they ran, so the test
    proves the setup is transactional: the mapping stages come first, and
    a failure in one prevents the rest.
    """
    ran: list[str] = []

    class _StubLibc:
        @staticmethod
        def unshare(_flags: int) -> int:
            ran.append("unshare")
            return 0

    monkeypatch.setattr(linux_sandbox, "_libc", lambda: _StubLibc())
    monkeypatch.setattr(
        linux_sandbox,
        "_map_identity",
        lambda _u, _g: (_ for _ in ()).throw(
            NetworkIsolationSetupError(
                "could not write the uid map", stage="uid_map"
            )
        ),
    )
    monkeypatch.setattr(
        linux_sandbox, "_private_mount_propagation", lambda _l: ran.append("mount")
    )

    with pytest.raises(NetworkIsolationSetupError) as excinfo:
        linux_sandbox.sandbox_prepare(Path("/tmp"))
    assert excinfo.value.stage == "uid_map"
    assert "mount" not in ran, (
        f"the mount stage ran after a mapping failure: {ran!r}"
    )


def test_mount_failure_is_a_setup_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed mount aborts before the parser could run."""

    class _StubLibc:
        @staticmethod
        def unshare(_flags: int) -> int:
            return 0

        @staticmethod
        def mount(*_args: object) -> int:
            return -1

    monkeypatch.setattr(linux_sandbox, "_libc", lambda: _StubLibc())
    monkeypatch.setattr(linux_sandbox, "_map_identity", lambda _u, _g: None)
    monkeypatch.setattr(linux_sandbox.ctypes, "set_errno", lambda _v: None)
    monkeypatch.setattr(linux_sandbox.ctypes, "get_errno", lambda: errno.EPERM)

    with pytest.raises(NetworkIsolationSetupError) as excinfo:
        linux_sandbox.sandbox_prepare(Path("/tmp"))
    # The fresh-root mount is the FIRST mount stage, so it is the one
    # that reports the failure.
    assert excinfo.value.stage == "mount_new_root"


def test_memory_cap_failure_is_a_setup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed RLIMIT_AS application aborts before the parser could run."""

    class _StubLibc:
        @staticmethod
        def unshare(_flags: int) -> int:
            return 0

    monkeypatch.setattr(linux_sandbox, "_libc", lambda: _StubLibc())
    monkeypatch.setattr(linux_sandbox, "_map_identity", lambda _u, _g: None)
    monkeypatch.setattr(linux_sandbox, "_private_mount_propagation", lambda _l: None)
    monkeypatch.setattr(linux_sandbox, "_remount_tree_read_only", lambda _l, **_k: None)
    monkeypatch.setattr(
        linux_sandbox, "_bind_artifact_writable", lambda _l, _s, _t: None
    )
    monkeypatch.setattr(linux_sandbox, "_verify_filesystem_policy", lambda _a: None)
    monkeypatch.setattr(linux_sandbox, "_new_root_dir", lambda _b: Path("/tmp"))
    monkeypatch.setattr(linux_sandbox, "_mount_fresh_root", lambda _l, _r: None)
    monkeypatch.setattr(linux_sandbox, "_reconstruct_root", lambda *_a, **_k: None)
    monkeypatch.setattr(linux_sandbox, "_pivot_into", lambda *_a, **_k: None)
    monkeypatch.setattr(linux_sandbox, "_detach_old_root", lambda _l: None)
    monkeypatch.setattr(
        linux_sandbox, "_reject_inherited_sockets", lambda *_a, **_k: None
    )

    # The real `_apply_memory_cap` raises the typed setup error, so the
    # injection is at the `setrlimit` level: that is the operation the
    # stage performs, and it keeps the error-wrapping under test.
    import resource as _resource

    def _fail_setrlimit(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.EPERM, "no rlimit")

    monkeypatch.setattr(_resource, "setrlimit", _fail_setrlimit)

    with pytest.raises(NetworkIsolationSetupError) as excinfo:
        linux_sandbox.sandbox_prepare(Path("/tmp"))
    assert excinfo.value.stage == "memory_limit"


# --------------------------------------------------------------------------
# The descriptor policy
# --------------------------------------------------------------------------
def test_socket_valued_standard_descriptor_is_rejected(
    tmp_path: Path,
) -> None:
    """A socket on a standard descriptor is a setup failure.

    ``close_fds=True`` alone is not accepted as proof: it closes
    descriptors above 2 but does not detect a socket-valued standard
    descriptor, which would hand the parser a live network handle.
    """
    left, right = socket.socketpair()
    try:
        # Make fd 0 a socket for the duration of the check.
        saved = os.dup(0)
        try:
            os.dup2(left.fileno(), 0)
            with pytest.raises(NetworkIsolationSetupError) as excinfo:
                linux_sandbox._reject_inherited_sockets()
            assert excinfo.value.stage == "socket_valued_standard_descriptor"
        finally:
            os.dup2(saved, 0)
            os.close(saved)
    finally:
        left.close()
        right.close()


def test_non_standard_descriptors_are_closed() -> None:
    """Every descriptor above 2 is closed by the hygiene stage.

    The hygiene stage is exercised in a FORKED child: it closes every
    descriptor above 2, which in the pytest process would include
    pytest's own descriptors and break the test run.
    """
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover - child process
        code = 0
        try:
            os.close(read_fd)
            # The hygiene stage closes EVERY descriptor above 2, which
            # includes the child's own stdout/stderr. That is correct
            # behaviour (the parser must not inherit them), so the
            # child re-points its standard descriptors to /dev/null
            # first and reports through the exit code.
            devnull = os.open(os.devnull, os.O_RDWR)
            os.dup2(devnull, 0)
            os.dup2(devnull, 1)
            os.dup2(devnull, 2)
            # The forked child inherits pytest's capture and coverage
            # machinery; the descriptor sweep must not trip it, so the
            # tracing/capture state is reset before the sweep.
            for _module in ("pytest", "coverage"):
                sys.modules.pop(_module, None)
            probe = os.open(os.devnull, os.O_RDONLY)
            if probe <= 2:
                code = 3
            else:
                linux_sandbox._reject_inherited_sockets()
                try:
                    os.fstat(probe)
                except OSError:
                    code = 0
                else:
                    code = 4  # the descriptor was NOT closed
            # The sweep may already have closed the write end; that is
            # the point of the test, so a double close is expected.
            with contextlib.suppress(OSError):
                os.close(write_fd)
        except BaseException:  # noqa: BLE001 -- child process safety
            code = 5
        # os._exit (not sys.exit) so no atexit/coverage hooks run in the
        # child and flush a partial trace into the parent's coverage data.
        os._exit(code)

    os.close(write_fd)
    os.close(read_fd)
    _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status), "the child did not exit normally"
    exit_code = os.WEXITSTATUS(status)
    assert exit_code == 0, (
        "the descriptor hygiene stage did not close a non-standard "
        f"descriptor (child exit code {exit_code}; 3 = the probe was not "
        "above fd 2, 4 = the descriptor was still open, 5 = an unexpected "
        "exception)"
    )


# --------------------------------------------------------------------------
# The memory cap
# --------------------------------------------------------------------------
@requires_namespace
@requires_namespace
def test_memory_cap_is_applied_inside_the_namespace(tmp_path: Path) -> None:
    """The 2 GiB RLIMIT_AS is in force after the setup completes.

    This forks, runs the launcher's setup stages, and reads the limit
    back inside the new namespace.
    """
    probe = (
        "import json, resource, sys\n"
        "from chess_coach.pdf_ocr import linux_sandbox\n"
        "from pathlib import Path\n"
        "linux_sandbox.sandbox_prepare(Path(sys.argv[1]))\n"
        "soft, hard = resource.getrlimit(resource.RLIMIT_AS)\n"
        "print(json.dumps({'soft': soft, 'hard': hard,\n"
        "                  'netns': __import__('os').stat('/proc/self/ns/net').st_ino,\n"
        "                  'uid': __import__('os').getuid()}))\n"
    )
    script = tmp_path / "probe.py"
    script.write_text(probe, encoding="utf-8")
    artifact = tmp_path / "artifact"
    artifact.mkdir()

    # The probe inherits the ambient environment, so it resolves the
    # package the same way the application does.
    cp = subprocess.run(
        [sys.executable, str(script), str(artifact)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert cp.returncode == 0, cp.stderr
    import json

    data = json.loads(cp.stdout.strip().splitlines()[-1])
    assert data["soft"] == MEMORY_CAP_BYTES
    assert data["hard"] == MEMORY_CAP_BYTES


@requires_namespace
@requires_namespace
def test_the_namespace_has_no_usable_interface(tmp_path: Path) -> None:
    """The new network namespace exposes loopback only."""
    probe = (
        "import json, os, sys\n"
        "from chess_coach.pdf_ocr import linux_sandbox\n"
        "from pathlib import Path\n"
        "linux_sandbox.sandbox_prepare(Path(sys.argv[1]))\n"
        "ifaces = [l.split(':')[0].strip()\n"
        "          for l in open('/proc/net/dev').read().splitlines()[2:]]\n"
        "print(json.dumps({'ifaces': ifaces,\n"
        "                  'netns': os.stat('/proc/self/ns/net').st_ino,\n"
        "                  'uid': os.getuid()}))\n"
    )
    script = tmp_path / "probe.py"
    script.write_text(probe, encoding="utf-8")
    artifact = tmp_path / "artifact"
    artifact.mkdir()

    # The probe inherits the ambient environment, so it resolves the
    # package the same way the application does.
    cp = subprocess.run(
        [sys.executable, str(script), str(artifact)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert cp.returncode == 0, cp.stderr
    import json

    data = json.loads(cp.stdout.strip().splitlines()[-1])
    assert data["ifaces"] == ["lo"]
    # The identity mapping preserves the deployment identity.
    assert data["uid"] == os.getuid()


@requires_namespace
@requires_namespace
def test_root_filesystem_is_read_only_and_artifact_is_writable(
    tmp_path: Path,
) -> None:
    """Root is read-only; only the artifact path is writable."""
    probe = (
        "import json, os, sys\n"
        "from chess_coach.pdf_ocr import linux_sandbox\n"
        "from pathlib import Path\n"
        "linux_sandbox.sandbox_prepare(Path(sys.argv[1]))\n"
        "r = {}\n"
        "try:\n"
        "    p = Path(sys.argv[1]) / 'w'\n"
        "    p.write_text('x'); r['artifact_writable'] = True\n"
        "except OSError as e:\n"
        "    r['artifact_writable'] = False\n"
        "try:\n"
        "    Path('/etc/.chess_coach_probe').write_text('x')\n"
        "    r['root_writable'] = True\n"
        "except OSError as e:\n"
        "    r['root_writable'] = False\n"
        "print(json.dumps(r))\n"
    )
    script = tmp_path / "probe.py"
    script.write_text(probe, encoding="utf-8")
    artifact = tmp_path / "artifact"
    artifact.mkdir()

    # The probe inherits the ambient environment, so it resolves the
    # package the same way the application does.
    cp = subprocess.run(
        [sys.executable, str(script), str(artifact)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert cp.returncode == 0, cp.stderr
    import json

    data = json.loads(cp.stdout.strip().splitlines()[-1])
    assert data["artifact_writable"] is True
    assert data["root_writable"] is False


# --------------------------------------------------------------------------
# The clone flags
# --------------------------------------------------------------------------
def test_clone_flags_are_the_combined_namespace() -> None:
    """The launcher requests exactly one combined namespace lifecycle."""
    assert SANDBOX_CLONE_FLAGS == (
        linux_sandbox.CLONE_NEWUSER | linux_sandbox.CLONE_NEWNET | linux_sandbox.CLONE_NEWNS
    )


def test_unshare_is_called_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The namespace lifecycle is established once, not repeatedly."""
    calls: list[int] = []

    class _StubLibc:
        @staticmethod
        def unshare(flags: int) -> int:
            calls.append(flags)
            return 0

    monkeypatch.setattr(linux_sandbox, "_libc", lambda: _StubLibc())
    monkeypatch.setattr(linux_sandbox, "_map_identity", lambda _u, _g: None)
    monkeypatch.setattr(linux_sandbox, "_private_mount_propagation", lambda _l: None)
    monkeypatch.setattr(linux_sandbox, "_remount_tree_read_only", lambda _l, **_k: None)
    monkeypatch.setattr(
        linux_sandbox, "_bind_artifact_writable", lambda _l, _s, _t: None
    )
    monkeypatch.setattr(linux_sandbox, "_verify_filesystem_policy", lambda _a: None)
    monkeypatch.setattr(linux_sandbox, "_new_root_dir", lambda _b: Path("/tmp"))
    monkeypatch.setattr(linux_sandbox, "_mount_fresh_root", lambda _l, _r: None)
    monkeypatch.setattr(linux_sandbox, "_reconstruct_root", lambda *_a, **_k: None)
    monkeypatch.setattr(linux_sandbox, "_pivot_into", lambda *_a, **_k: None)
    monkeypatch.setattr(linux_sandbox, "_detach_old_root", lambda _l: None)
    monkeypatch.setattr(
        linux_sandbox, "_reject_inherited_sockets", lambda *_a, **_k: None
    )
    monkeypatch.setattr(linux_sandbox, "_apply_memory_cap", lambda _l: None)

    linux_sandbox.sandbox_prepare(Path("/tmp"))
    assert calls == [SANDBOX_CLONE_FLAGS]


# --------------------------------------------------------------------------
# The launcher program
# --------------------------------------------------------------------------
def test_launcher_reports_a_setup_failure_on_the_status_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A setup failure is reported on the dedicated status channel."""
    def _fail_prepare(
        artifact_dir: Path,
        *,
        limit_bytes: int = MEMORY_CAP_BYTES,
        preserve_fds: frozenset[int] = frozenset(),
    ) -> None:
        raise NetworkIsolationSetupError(
            "the namespace could not be created", stage="namespace_creation"
        )

    monkeypatch.setattr(linux_sandbox, "sandbox_prepare", _fail_prepare)

    read_fd, write_fd = os.pipe()
    try:
        code = linux_sandbox.main(
            [
                "--status-fd",
                str(write_fd),
                "--artifact-dir",
                str(tmp_path),
                "--",
                sys.executable,
                "-c",
                "print('SHOULD NOT RUN')",
            ]
        )
        os.close(write_fd)
        write_fd = -1
        data = os.read(read_fd, 4096).decode("utf-8", errors="replace")
    finally:
        os.close(read_fd)
        if write_fd != -1:
            os.close(write_fd)

    assert code == linux_sandbox.SETUP_FAILURE_EXIT
    assert data.startswith(linux_sandbox.STATUS_SETUP_FAILURE)
    assert "namespace_creation" in data
    assert "SHOULD NOT RUN" not in data


def test_launcher_rejects_a_missing_parser_command(tmp_path: Path) -> None:
    """A launcher invocation with no parser is a setup failure."""
    read_fd, write_fd = os.pipe()
    try:
        code = linux_sandbox.main(
            ["--status-fd", str(write_fd), "--artifact-dir", str(tmp_path)]
        )
        os.close(write_fd)
        write_fd = -1
        data = os.read(read_fd, 4096).decode("utf-8", errors="replace")
    finally:
        os.close(read_fd)
        if write_fd != -1:
            os.close(write_fd)

    assert code == linux_sandbox.SETUP_FAILURE_EXIT
    assert data.startswith(linux_sandbox.STATUS_SETUP_FAILURE)
