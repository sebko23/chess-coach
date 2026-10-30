"""A-F11 PDF-parser sandbox launcher for Linux.

This module is the **single owner** of the parser's containment boundary on
Linux. It is invoked as a separate program with a controlled argv protocol
(no shell string is ever evaluated) and performs one namespace lifecycle
(``CLONE_NEWUSER | CLONE_NEWNET | CLONE_NEWNS``) before it ``exec``s the
parser:

1. ``unshare(CLONE_NEWUSER | CLONE_NEWNET | CLONE_NEWNS)`` -- exactly once.
2. UID/GID identity mapping that preserves the deployment identity.
3. Private mount propagation.
4. Root filesystem remounted read-only; only the artifact path stays writable.
5. Descriptor hygiene: every non-standard descriptor closed, and an inherited
   socket-valued standard descriptor rejected.
6. The 2 GiB per-process ``RLIMIT_AS`` applied.
7. ``exec`` of the parser.

Every stage is checked. **Any failure aborts before ``exec``**, so an
unconstrained parser is never started. There is no fallback to direct
execution, proxy stripping, a source-tree copy, or an unconstrained
subprocess.

Why a dedicated launcher rather than ``subprocess.Popen(preexec_fn=...)``:
``preexec_fn`` runs inside the forked child and cannot report *which* setup
stage failed through a dedicated status channel, so a setup failure would be
indistinguishable from a parser failure. The launcher reports the failing
stage over a dedicated status file descriptor, and only ``exec``s the
parser after every stage has succeeded.

Deployment note: Docker's default seccomp profile allows ``unshare``,
``clone``, ``mount`` and ``setns`` only under ``CAP_SYS_ADMIN``, so a
non-root container cannot establish this boundary with the default profile.
The backend image therefore ships a narrow seccomp profile
(``infra/docker/seccomp-backend.json``) that allows exactly the
namespace/mount/identity syscalls this launcher needs, and nothing else.
Without that profile the launcher fails closed with
:class:`NetworkIsolationSetupError`.
"""
from __future__ import annotations

import contextlib
import ctypes
import ctypes.util
import errno
import os
import socket
import sys
from collections.abc import Sequence
from pathlib import Path

from chess_coach.errors import ChessCoachError, ErrorCode

# `resource` is a Unix-only stdlib module. This module is imported by the
# shared runner on every platform (to branch on the capability flag), so the
# import must be guarded even though the launcher only executes on Linux.
if sys.platform != "win32":
    import resource  # noqa: E402  -- Unix-only; gated by the platform check above

# --------------------------------------------------------------------------
# Clone / mount constants (from <linux/sched.h> and <sys/mount.h>)
# --------------------------------------------------------------------------
CLONE_NEWNS = 0x00020000
CLONE_NEWUSER = 0x10000000
CLONE_NEWNET = 0x40000000
SANDBOX_CLONE_FLAGS = CLONE_NEWUSER | CLONE_NEWNET | CLONE_NEWNS

MS_RDONLY = 1
MS_REMOUNT = 32
MNT_DETACH = 2
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
MS_BIND = 4096
MS_PRIVATE = 1 << 18
MS_REC = 16384

#: The A-F11 property-4 memory cap: 2 GiB of address space per process.
MEMORY_CAP_BYTES = 2 * 1024 * 1024 * 1024

#: The status file descriptor the launcher writes its outcome to.
STATUS_FD = 3

#: Status line prefixes. The gateway distinguishes them by prefix.
STATUS_OK = "OK"
STATUS_SETUP_FAILURE = "SETUP_FAILURE"

#: The launcher's exit code when a setup stage failed.
SETUP_FAILURE_EXIT = 97


class NetworkIsolationSetupError(ChessCoachError):
    """A containment setup stage failed, so the parser was never executed.

    This is an internal server-side failure, never a client error: the
    deployment could not establish the sandbox, which is a different
    condition from a malformed PDF (400), a missing tool (422), a timeout
    (504), a memory-limit hit (422), or an unsupported platform (501).

    ``stage`` names the exact setup stage that failed so the outcome is
    auditable without re-running the process.
    """

    code = ErrorCode.NETWORK_ISOLATION_SETUP_FAILED
    http_status = 500

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        details: dict[str, object] | None = None,
    ) -> None:
        merged: dict[str, object] = {"stage": stage}
        if details:
            merged.update(details)
        super().__init__(message, details=merged)
        self.stage = stage


# --------------------------------------------------------------------------
# libc access
# --------------------------------------------------------------------------
def _libc() -> ctypes.CDLL:
    name = ctypes.util.find_library("c")
    if name is None:  # pragma: no cover - libc is always present on Linux
        raise NetworkIsolationSetupError(
            "could not locate the C library", stage="libc_lookup"
        )
    lib = ctypes.CDLL(name, use_errno=True)
    lib.unshare.argtypes = [ctypes.c_int]
    lib.unshare.restype = ctypes.c_int
    lib.mount.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    lib.mount.restype = ctypes.c_int
    return lib


def _fail(stage: str, message: str, **details: object) -> NetworkIsolationSetupError:
    return NetworkIsolationSetupError(message, stage=stage, details=details)


# --------------------------------------------------------------------------
# Setup stages. Each raises NetworkIsolationSetupError on failure.
# --------------------------------------------------------------------------
def _unshare(lib: ctypes.CDLL) -> None:
    ctypes.set_errno(0)
    rc = lib.unshare(SANDBOX_CLONE_FLAGS)
    if rc != 0:
        err = ctypes.get_errno() or 0
        raise _fail(
            "namespace_creation",
            "could not create the sandbox namespace",
            errno=err,
            errno_name=errno.errorcode.get(err, str(err)),
            clone_flags=SANDBOX_CLONE_FLAGS,
        )


def _write_map(path: str, content: str, stage: str) -> None:
    try:
        with open(path, "w", encoding="ascii") as handle:
            handle.write(content)
    except OSError as exc:
        raise _fail(
            stage,
            f"could not write {path}",
            errno=exc.errno,
            errno_name=errno.errorcode.get(exc.errno or 0, str(exc.errno)),
            path=path,
        ) from exc


def _map_identity(uid: int, gid: int) -> None:
    """Write the identity UID/GID maps.

    ``setgroups`` must be denied *before* the GID map is written; the
    kernel refuses ``gid_map`` otherwise for an unprivileged writer.

    The map is an **identity** mapping (``1000 1000 1``): the process keeps
    the deployment identity's uid/gid, so it retains ownership of, and
    access to, the artifact path. The directive's stated preference is
    identity mapping unless another mapping is proven necessary.
    """
    _write_map("/proc/self/setgroups", "deny", "setgroups_denial")
    _write_map("/proc/self/uid_map", f"{uid} {uid} 1\n", "uid_map")
    _write_map("/proc/self/gid_map", f"{gid} {gid} 1\n", "gid_map")


def _mount_propagation_state(path: str = "/") -> str:
    """Describe the propagation state of a mount, for diagnostics.

    The launcher's setup errors travel on the status channel, so the
    reason a mount stage failed must be recoverable from a CI log
    without a shell in the sandbox.
    """
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) < 6:
                    continue
                mount_point = parts[4]
                if mount_point != path:
                    continue
                optional = parts[6] if len(parts) > 6 else ""
                known = {"shared", "master", "private", "slave", "unbindable"}
                flags = [f for f in optional.split(",") if f in known]
                state = "|".join(flags) if flags else "no-propagation-flag"
                return f"{path} {state} {parts[2]}"
    except OSError:
        pass
    return f"{path} unknown"


def _new_root_dir(base: Path) -> Path:
    """Create the mountpoint for the launcher's own root.

    It lives beside the artifact directory, which is a writable path
    that exists in the supported deployment, so the mountpoint can be
    created before the root filesystem is made read-only.
    """
    root = base / ".sandbox-root"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _fail(
            "mount_new_root",
            "could not create the sandbox root mountpoint",
            errno=exc.errno,
            errno_name=errno.errorcode.get(exc.errno or 0, str(exc.errno)),
            path=str(root),
        ) from exc
    return root


def _mount_fresh_root(lib: ctypes.CDLL, root: Path) -> None:
    """Mount a fresh tmpfs as the launcher's own root.

    A mount INHERITED from the parent mount namespace is locked when
    the process that created it lacked CAP_SYS_ADMIN in the namespace
    that owns it, and a locked mount's propagation cannot be changed --
    the kernel refuses the operation with EACCES. A tmpfs created
    HERE, inside this process's own user and mount namespace, is never
    inherited and never locked, so its propagation and its flags are
    the launcher's to set.

    This is what makes the containment sequence work in a deployment
    whose root mount is locked.
    """
    ctypes.set_errno(0)
    rc = lib.mount(
        b"tmpfs",
        str(root).encode(),
        b"tmpfs",
        MS_NOSUID | MS_NODEV,
        None,
    )
    if rc != 0:
        err = ctypes.get_errno() or 0
        raise _fail(
            "mount_new_root",
            "could not mount the sandbox root",
            errno=err,
            errno_name=errno.errorcode.get(err, str(err)),
            path=str(root),
        )


def _make_mountpoint(path: Path) -> None:
    """Create a mountpoint directory, reporting the failing stage."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _fail(
            "mount_artifact_bind",
            "could not create the artifact mountpoint",
            errno=exc.errno,
            errno_name=errno.errorcode.get(exc.errno or 0, str(exc.errno)),
            path=str(path),
        ) from exc


def _reconstruct_root(lib: ctypes.CDLL, root: Path, skip: str) -> None:
    """Fill the fresh root with the old root's content.

    Each top-level entry of the current root is recursively
    bind-mounted into the new root, so the parser finds the absolute
    paths it expects: `/usr/local/bin/pdftoppm`, the shared libraries,
    `/etc/ld.so.cache`, and so on.

    The entries are bound individually rather than binding the whole
    root in one call, so that `root/oldroot` stays on the new root's
    own tmpfs and can serve as `pivot_root`'s put_old directory.

    Each of these binds is created inside the sandbox's own mount
    namespace, so none of them is locked and every one of them can be
    remounted.
    """
    try:
        entries = sorted(os.listdir("/"))
    except OSError as exc:
        raise _fail(
            "mount_reconstruct_root",
            "could not read the root directory",
            errno=exc.errno,
            errno_name=errno.errorcode.get(exc.errno or 0, str(exc.errno)),
        ) from exc
    for name in entries:
        if name == skip:
            continue
        source = f"/{name}"
        target = root / name
        if os.path.isdir(source):
            _make_mountpoint(target)
        else:
            # A regular file cannot be a mountpoint, so it is bound
            # onto an existing empty file of the same name.
            try:
                target.touch(exist_ok=True)
            except OSError as exc:
                raise _fail(
                    "mount_reconstruct_root",
                    "could not create a root file mountpoint",
                    errno=exc.errno,
                    errno_name=errno.errorcode.get(exc.errno or 0, str(exc.errno)),
                    path=str(target),
                ) from exc
        ctypes.set_errno(0)
        rc = lib.mount(
            source.encode(), str(target).encode(), None, MS_BIND | MS_REC, None
        )
        if rc != 0:
            err = ctypes.get_errno() or 0
            raise _fail(
                "mount_reconstruct_root",
                "could not bind a root entry into the sandbox root",
                errno=err,
                errno_name=errno.errorcode.get(err, str(err)),
                path=source,
            )


def _bind_artifact_writable(lib: ctypes.CDLL, source: Path, target: Path) -> None:
    """Bind-mount `source` at `target`, then make `target` writable.

    The bind must be remounted separately: a bind of a read-only
    source inherits the read-only flag, so the target would stay
    read-only without the second call.
    """
    source_b = str(source).encode()
    target_b = str(target).encode()
    ctypes.set_errno(0)
    rc = lib.mount(source_b, target_b, None, MS_BIND, None)
    if rc != 0:
        err = ctypes.get_errno() or 0
        raise _fail(
            "mount_artifact_bind",
            "could not bind-mount the artifact directory",
            errno=err,
            errno_name=errno.errorcode.get(err, str(err)),
            artifact_dir=str(source),
        )
    ctypes.set_errno(0)
    rc = lib.mount(b"none", target_b, None, MS_REMOUNT | MS_BIND, None)
    if rc != 0:
        err = ctypes.get_errno() or 0
        raise _fail(
            "mount_artifact_writable",
            "could not make the artifact directory writable",
            errno=err,
            errno_name=errno.errorcode.get(err, str(err)),
            artifact_dir=str(target),
        )


def _pivot_into(lib: ctypes.CDLL, root: Path) -> None:
    """Pivot into the fresh root and detach the old one.

    `pivot_root` makes the fresh tmpfs the process's root and puts the
    old root under `<root>/oldroot`, where it can be unmounted. The
    old root is then unreachable: the sandbox has no path back to the
    host filesystem.
    """
    old = root / "oldroot"
    _make_mountpoint(old)
    libc = _libc()
    libc.pivot_root.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    libc.pivot_root.restype = ctypes.c_int
    ctypes.set_errno(0)
    rc = libc.pivot_root(str(root).encode(), str(old).encode())
    if rc != 0:
        err = ctypes.get_errno() or 0
        raise _fail(
            "pivot_root",
            "could not pivot into the sandbox root",
            errno=err,
            errno_name=errno.errorcode.get(err, str(err)),
        )
    os.chdir("/")


def _detach_old_root(lib: ctypes.CDLL) -> None:
    """Detach the old root after the pivot.

    `pivot_root` moves the old root to `/oldroot`; unmounting it
    leaves the sandbox with no path back to the host filesystem.
    """
    ctypes.set_errno(0)
    rc = lib.umount2(b"/oldroot", MNT_DETACH)
    if rc != 0:
        err = ctypes.get_errno() or 0
        raise _fail(
            "pivot_root",
            "could not detach the old root",
            errno=err,
            errno_name=errno.errorcode.get(err, str(err)),
        )


def _remount_tree_read_only(lib: ctypes.CDLL, writable: Path | None = None) -> None:
    """Make the whole new root read-only except the writable path.

    The root tmpfs and each of the binds are separate mounts, so each
    is remounted individually. Every one of them was created inside
    the sandbox's own mount namespace, so none is locked and each
    remount is permitted.

    A mount that is still locked -- one inherited from the container
    runtime, such as /dev -- cannot be remounted. It is DETACHED
    instead: the sandbox does not need the host's device nodes, and
    leaving them reachable would be exactly the exposure the sandbox
    exists to prevent.
    """
    ctypes.set_errno(0)
    rc = lib.mount(b"none", b"/", None, MS_REMOUNT | MS_BIND | MS_RDONLY, None)
    if rc != 0:
        err = ctypes.get_errno() or 0
        raise _fail(
            "mount_root_read_only",
            "could not remount the root filesystem read-only",
            errno=err,
            errno_name=errno.errorcode.get(err, str(err)),
        )
    try:
        entries = sorted(os.listdir("/"))
    except OSError:
        return
    writable_str = str(writable) if writable is not None else None
    for name in entries:
        target = f"/{name}"
        if writable_str is not None and target == writable_str:
            # The artifact path is the one writable path by policy.
            continue
        if target == "/oldroot":
            # The old root was detached with MNT_DETACH, which is a
            # LAZY unmount: the entry stays in the mount table until
            # the last reference goes away. The old root is not
            # reachable through it, so it is skipped here.
            continue
        if target == "/proc":
            # /proc is a recursive bind created inside the sandbox's
            # own mount namespace. It is NOT detached: the parser
            # needs it, and it exposes the sandbox's own pidns and
            # netns because the mount namespace is the sandbox's.
            continue
        if not os.path.isdir(target):
            # A regular-file bind is already read-only by virtue of the
            # read-only filesystem it was bound from.
            continue
        ctypes.set_errno(0)
        rc = lib.mount(
            b"none", target.encode(), None, MS_REMOUNT | MS_BIND | MS_RDONLY, None
        )
        if rc == 0:
            continue
        err = ctypes.get_errno() or 0
        if err == errno.EPERM:
            ctypes.set_errno(0)
            detach_rc = lib.umount2(target.encode(), MNT_DETACH)
            if detach_rc != 0:
                detach_err = ctypes.get_errno() or 0
                raise _fail(
                    "mount_root_read_only",
                    "could not detach a locked root entry",
                    errno=detach_err,
                    errno_name=errno.errorcode.get(detach_err, str(detach_err)),
                    path=target,
                )
            continue
        raise _fail(
            "mount_root_read_only",
            "could not remount a root entry read-only",
            errno=err,
            errno_name=errno.errorcode.get(err, str(err)),
            path=target,
        )


def _private_mount_propagation(lib: ctypes.CDLL) -> None:
    ctypes.set_errno(0)
    rc = lib.mount(b"none", b"/", None, MS_REC | MS_PRIVATE, None)
    if rc != 0:
        err = ctypes.get_errno() or 0
        raise _fail(
            "mount_private_propagation",
            "could not make mount propagation private",
            errno=err,
            errno_name=errno.errorcode.get(err, str(err)),
            propagation=_mount_propagation_state("/"),
            caps=_effective_capabilities(),
        )


def _effective_capabilities() -> str:
    """The effective capability mask, for diagnostics."""
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("CapEff:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


def _verify_filesystem_policy(artifact_dir: Path) -> None:
    """Prove the artifact path is writable and the root filesystem is not."""
    probe = artifact_dir / ".chess_coach_sandbox_write_probe"
    try:
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("probe")
        probe.unlink()
    except OSError as exc:
        raise _fail(
            "artifact_not_writable",
            "the artifact directory is not writable by the sandboxed identity",
            errno=exc.errno,
            errno_name=errno.errorcode.get(exc.errno or 0, str(exc.errno)),
            artifact_dir=str(artifact_dir),
        ) from exc

    root_probe = Path("/etc/.chess_coach_sandbox_write_probe")
    try:
        with open(root_probe, "w", encoding="utf-8") as handle:
            handle.write("probe")
    except OSError:
        return
    else:
        root_probe.unlink(missing_ok=True)
        raise _fail(
            "root_filesystem_writable",
            "the root filesystem is still writable; the read-only policy "
            "was not established",
        )


def _reject_inherited_sockets(preserve: frozenset[int] = frozenset()) -> None:
    """Close every non-standard descriptor and reject inherited sockets.

    ``close_fds=True`` alone is not accepted as proof: it closes
    descriptors above 2 but does not *detect* a socket-valued standard
    descriptor, which would hand the parser a live network handle. A
    socket on any standard descriptor is a setup failure.

    ``preserve`` names the descriptors that are part of the launcher's
    own control plane and must survive the hygiene stage -- specifically
    the **status channel** the launcher reports its outcome on. Closing it
    would leave the gateway unable to distinguish "setup failed" from
    "the launcher died", which is exactly the distinction the status
    channel exists to make.
    """
    for fd in (0, 1, 2):
        try:
            sock = socket.socket(fileno=fd)
        except OSError:
            continue
        sock.detach()
        raise _fail(
            "socket_valued_standard_descriptor",
            "a standard descriptor is a socket; the parser would inherit "
            "a live network handle",
            fd=fd,
        )

    for fd in range(3, 4096):
        if fd in preserve:
            continue
        with contextlib.suppress(OSError):
            os.close(fd)


def _apply_memory_cap(limit_bytes: int = MEMORY_CAP_BYTES) -> None:
    if sys.platform == "win32":  # pragma: no cover - Linux-only path
        raise _fail("memory_limit", "the memory cap is a Linux-only mechanism")
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
    except (ValueError, OSError) as exc:
        raise _fail(
            "memory_limit",
            "could not apply the per-process memory cap",
            errno=getattr(exc, "errno", None),
            limit_bytes=limit_bytes,
        ) from exc
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    if soft != limit_bytes:
        raise _fail(
            "memory_limit",
            "the per-process memory cap was not applied",
            soft=soft,
            hard=hard,
            limit_bytes=limit_bytes,
        )


def sandbox_prepare(
    artifact_dir: Path,
    *,
    limit_bytes: int = MEMORY_CAP_BYTES,
    preserve_fds: frozenset[int] = frozenset(),
) -> None:
    """Establish the whole sandbox policy. Raises on any stage failure.

    Every stage is checked; the first failure raises
    :class:`NetworkIsolationSetupError` and the parser is never executed.

    ``preserve_fds`` names descriptors that belong to the launcher's own
    control plane (the status channel) and must survive the descriptor
    hygiene stage.
    """
    # The deployment identity MUST be captured BEFORE the unshare: once
    # CLONE_NEWUSER is active the UID map is still empty, so `os.getuid()`
    # reports the overflow uid (65534) rather than the real one. Writing
    # that overflow uid into uid_map is rejected by the kernel, because the
    # writer may only map the uid it actually held in the parent namespace.
    uid = os.getuid()
    gid = os.getgid()

    lib = _libc()
    _unshare(lib)
    _map_identity(uid, gid)

    # Build the launcher's OWN root rather than operating on the
    # inherited one. A mount inherited from the parent mount namespace
    # is locked when the process that created it lacked CAP_SYS_ADMIN
    # in the namespace that owns it, and a locked mount's propagation
    # cannot be changed -- the kernel refuses with EACCES. A tmpfs
    # created here is never inherited and never locked.
    root = _new_root_dir(artifact_dir.parent)
    _mount_fresh_root(lib, root)
    # Fill the new root with the old root's content, so the parser
    # finds the absolute paths it expects.
    _reconstruct_root(lib, root, skip=root.name)
    # The artifact is bound at its ORIGINAL absolute path inside the new
    # root, so the parser's argv -- which names that path -- still
    # resolves after the pivot.
    try:
        relative = artifact_dir.relative_to("/")
    except ValueError:
        relative = Path(artifact_dir.name)
    _make_mountpoint(root / relative)
    _bind_artifact_writable(lib, artifact_dir, root / relative)
    _pivot_into(lib, root)
    # The new root is ours: its propagation is ours to set.
    _private_mount_propagation(lib)
    # The old root is detached BEFORE the tree is remounted: after the
    # pivot it is visible as /oldroot, and it is the old, writable root.
    _detach_old_root(lib)
    # The root tree is made read-only except for the artifact path.
    _remount_tree_read_only(lib, writable=artifact_dir)
    _verify_filesystem_policy(artifact_dir)
    _reject_inherited_sockets(preserve_fds)
    _apply_memory_cap(limit_bytes)


# --------------------------------------------------------------------------
# The launcher program
# --------------------------------------------------------------------------
def _write_status(fd: int, line: str) -> None:
    with contextlib.suppress(OSError):
        os.write(fd, f"{line}\n".encode())


def build_launcher_argv(
    parser_argv: Sequence[str],
    *,
    artifact_dir: Path,
    limit_bytes: int = MEMORY_CAP_BYTES,
    status_fd: int = STATUS_FD,
) -> list[str]:
    """Build the launcher's controlled argv. No shell string is evaluated."""
    return [
        sys.executable,
        "-m",
        "chess_coach.pdf_ocr.linux_sandbox",
        "--status-fd",
        str(status_fd),
        "--artifact-dir",
        str(artifact_dir),
        "--limit-bytes",
        str(limit_bytes),
        "--",
        *parser_argv,
    ]


def _parse_args(argv: Sequence[str]) -> tuple[int, Path, int, list[str]]:
    status_fd = STATUS_FD
    artifact_dir = ""
    limit_bytes = MEMORY_CAP_BYTES
    parser_argv: list[str] = []
    args = list(argv)
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == "--":
            parser_argv = args[index + 1 :]
            break
        if argument == "--status-fd":
            index += 1
            status_fd = int(args[index])
        elif argument == "--artifact-dir":
            index += 1
            artifact_dir = args[index]
        elif argument == "--limit-bytes":
            index += 1
            limit_bytes = int(args[index])
        else:
            raise SystemExit(f"unknown launcher argument: {argument}")
        index += 1
    return status_fd, Path(artifact_dir), limit_bytes, parser_argv


def main(argv: Sequence[str] | None = None) -> int:
    """The launcher program entry point.

    Writes ``OK`` to the status descriptor only after every containment
    stage has succeeded, then ``exec``s the parser. A setup failure
    writes ``SETUP_FAILURE <stage>\\x00<message>`` and exits without ever
    executing the parser.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        status_fd, artifact_dir, limit_bytes, parser_argv = _parse_args(args)
    except (SystemExit, ValueError) as exc:
        print(f"launcher argument error: {exc}", file=sys.stderr)
        return SETUP_FAILURE_EXIT

    if not parser_argv:
        _write_status(status_fd, f"{STATUS_SETUP_FAILURE} argv\x00no parser command was given")
        return SETUP_FAILURE_EXIT

    try:
        sandbox_prepare(
            artifact_dir,
            limit_bytes=limit_bytes,
            preserve_fds=frozenset({status_fd}),
        )
    except NetworkIsolationSetupError as exc:
        # The diagnostic details travel with the status line: a setup
        # failure that only says "could not make mount propagation
        # private" is not diagnosable from a CI log.
        #
        # The format is `SETUP_FAILURE <stage>\x00<message> [details]`.
        # The `\x00` separator is what the gateway parses to recover the
        # failing stage, so it must be preserved exactly; the optional
        # diagnostics go AFTER the message and are part of it.
        detail = exc.details.get("errno_name") or exc.details.get("errno")
        extra = {
            key: value
            for key, value in exc.details.items()
            if key not in {"errno", "errno_name"} and value is not None
        }
        message = exc.message
        if detail:
            message = f"{message} [{detail}]"
        for key, value in extra.items():
            message = f"{message} {key}={value}"
        _write_status(
            status_fd,
            f"{STATUS_SETUP_FAILURE} {exc.stage}\x00{message}",
        )
        return SETUP_FAILURE_EXIT
    except BaseException as exc:  # noqa: BLE001
        _write_status(status_fd, f"{STATUS_SETUP_FAILURE} unexpected\x00{exc!r}")
        return SETUP_FAILURE_EXIT

    # Every containment stage succeeded. Tell the gateway, then close the
    # status channel and exec the parser.
    #
    # The status descriptor MUST be closed before the exec: otherwise the
    # parser inherits the control channel, which (a) lets the untrusted
    # parser write to the launcher's status channel and forge a result,
    # and (b) keeps the write end open, so the gateway's read cannot
    # observe the OK line until the parser exits. Closing it makes the
    # gateway see the OK line and EOF immediately, and the parser cannot
    # touch the channel at all.
    # The status descriptor is closed AT exec by the kernel (FD_CLOEXEC),
    # not closed here. Closing it here would mean an exec failure could
    # not be reported: the gateway would read "OK" and then see the
    # failure exit code with no explanation. With FD_CLOEXEC the parser
    # never inherits the channel, and a failed exec can still be
    # reported on it.
    with contextlib.suppress(OSError):
        os.set_inheritable(status_fd, False)
    _write_status(status_fd, STATUS_OK)
    try:
        os.execv(parser_argv[0], parser_argv)  # noqa: S606  -- intentional: the parser exec
    except OSError as exc:
        _write_status(status_fd, f"{STATUS_SETUP_FAILURE} exec\x00{exc}")
        return SETUP_FAILURE_EXIT
    return SETUP_FAILURE_EXIT  # pragma: no cover - exec does not return


if __name__ == "__main__":  # pragma: no cover - program entry point
    sys.exit(main())
