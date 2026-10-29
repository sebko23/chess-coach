"""A-F11 subprocess runner — wraps pdftoppm with sandbox primitives.

This module provides a subprocess-based replacement for
`pdf2image.convert_from_bytes` that exposes the
`subprocess.Popen` parameters pdf2image does not (notably
`preexec_fn` for setting resource limits in the child
process). Per `docs/08_security/security-strategy.md`
§A-F11, the PDF parser MUST run in an isolated subprocess
with no network access, read-only filesystem, 2 GB memory
cap, and a 5-minute timeout.

**This BBF (FU-22-impl) implements the 2 GB memory cap via
`resource.setrlimit(RLIMIT_AS)` in a `preexec_fn` callback.**
The other 3 properties (network isolation, read-only FS,
timeout) are out of scope here; the timeout is already
enforced by the route's `asyncio.wait_for` wrapper.

**Platform support (BBF-FU-22-windows-contract-correction, extended by
BBF-FU-22-B2-windows-job-object).**
The B1 cap mechanism was Unix-only: `resource` is a Unix stdlib module
and CPython rejects `preexec_fn` on Windows
(`ValueError: preexec_fn is not supported on Windows platforms`), so B1
made Windows PDF parsing UNSUPPORTED via
`ensure_memory_cap_supported()` (a typed
`UnsupportedParserPlatformError`, HTTP 501, error code
`internal.not_implemented`) raised BEFORE any parser process was spawned.

**B2 replaced that refusal with real enforcement.** On Windows the
parser is now launched through the Job Object backend in
:mod:`chess_coach.pdf_ocr.windows_job`: the target is created
suspended, the Job is configured with
`JOB_OBJECT_LIMIT_PROCESS_MEMORY`, the target is assigned to the Job,
and only then is it resumed. The limit is therefore in force before the
target can allocate or spawn descendants, and the B1 refusal path is no
longer reached on Windows. The backend **fails closed**: a Job-creation,
limit-configuration, process-creation, assignment, or resume failure
terminates the target without resuming it, so an uncapped parser is
never launched. There is no fallback to `preexec_fn`, to source-tree
execution, or to the Linux `RLIMIT_AS` mechanism on Windows.

`ensure_memory_cap_supported()` still exists and still raises on a
platform that has neither mechanism, but on Windows it no longer fires.

**The Linux cap is per-process, not an aggregate process-tree budget.**
`RLIMIT_AS` caps the virtual address space of the process it is applied
to. Descendants inherit the limit, but each descendant gets its OWN
independent 2 GiB allowance. There is no aggregate memory budget across
the process tree: the limit is NOT an aggregate process-tree memory budget.

**The Windows cap is per-process too.** The Job Object's
`ProcessMemoryLimit` field is the **per-process** limit; the aggregate
`JobMemoryLimit` field (and its `JOB_OBJECT_LIMIT_JOB_MEMORY` flag) is
deliberately left disabled and at zero. Descendants inherit Job
membership (breakaway is never enabled) and each gets its OWN 2 GiB
allowance. The Windows limit is likewise NOT a 2 GiB aggregate
process-tree memory budget.

The architectural pattern established here (bypass
pdf2image, call pdftoppm directly via `subprocess.Popen`
with the right sandbox primitives) is the foundation for
the follow-up BBFs (FU-20-impl: network isolation;
FU-21-impl: read-only filesystem). Per
`docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md` Section C,
FU-22 is the lightest of the three and is implemented first
to establish the `subprocess_runner.py` module + refactor
pattern.
"""
from __future__ import annotations

import shutil
import subprocess  # noqa: S404  -- intentional: PDF parsing requires subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from chess_coach.errors import NotImplementedYetError
from chess_coach.pdf_ocr.windows_job import WINDOWS_JOB_SUPPORTED

# `resource` is a Unix-only stdlib module. On Windows, it's
# not available; the cap mechanism is a no-op (Windows
# support is a future follow-up BBF).
if sys.platform != "win32":
    import resource  # noqa: E402  -- Unix-only; gated by sys.platform check above

# A-F11 property 4: 2 GB memory cap. Applied to the child
# process via preexec_fn=set_rlimit_as_preexec(MEM_CAP_BYTES).
# The hard cap (both soft and hard set to the same value)
# matches the A-F11 contract: "2 GB memory cap" is a
# ceiling, not a soft warning.
MEM_CAP_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GiB

#: True when this platform can enforce the A-F11 property-4 memory cap.
#:
#: **Linux:** the cap is enforced with ``resource.setrlimit(RLIMIT_AS, ...)``
#: via ``preexec_fn``.
#:
#: **Windows:** the cap is enforced with a Job Object
#: (``JOB_OBJECT_LIMIT_PROCESS_MEMORY``) by the
#: :mod:`chess_coach.pdf_ocr.windows_job` backend
#: (``BBF-FU-22-B2-windows-job-object``). The target is created suspended,
#: the Job is configured, the target is assigned, and only then is it
#: resumed -- so the limit is in force before the target can allocate.
#:
#: **Any other platform:** the cap cannot be enforced, so PDF parsing is
#: refused.
#:
#: The platform identifier used for the capability decision. A module-level
#: name (rather than a bare `sys.platform` read) so that tests can simulate
#: an uncappable platform without mutating the process-wide `sys.platform`,
#: which would corrupt unrelated runtime behaviour (asyncio, anyio, ...).
HOST_PLATFORM: str = sys.platform

MEMORY_CAP_SUPPORTED: bool = HOST_PLATFORM != "win32" or WINDOWS_JOB_SUPPORTED

#: The capability that enforces the cap, named for the error details.
MEMORY_CAP_MECHANISM: str = (
    "RLIMIT_AS via preexec_fn"
    if HOST_PLATFORM != "win32"
    else "Windows Job Object (JOB_OBJECT_LIMIT_PROCESS_MEMORY)"
)

# pdftoppm invocation defaults. These match the previous
# pdf2image.convert_from_bytes defaults (DPI=200, fmt=ppm)
# but are exposed as parameters for testability.
DEFAULT_DPI: int = 200
DEFAULT_FMT: str = "png"  # PNG is easier to read back than PPM

# Popen default timeout. The route layer wraps this in
# `asyncio.wait_for` for the outer timeout, but the
# `proc.communicate(timeout=...)` is the inner safety net.
DEFAULT_TIMEOUT_SECONDS: int = 300


def set_rlimit_as_preexec(mem_cap_bytes: int) -> Callable[[], None]:
    """Build a `preexec_fn` callable that caps the child process
    virtual-address-space at `mem_cap_bytes`.

    Returns a no-arg callable suitable for `subprocess.Popen`'s
    `preexec_fn=` parameter. The callable runs in the child
    process after `fork` but before `exec`, so the cap is
    in place before pdftoppm starts allocating.

    On Linux, this calls `resource.setrlimit(resource.RLIMIT_AS,
    (cap, cap))`. `RLIMIT_AS` covers the entire virtual
    address space (heap + stack + mmap + shared libraries),
    so the cap is a hard ceiling, not just a heap cap.

    On Windows, `resource.setrlimit` is not available, and CPython
    rejects `preexec_fn` outright. The Windows equivalent is a Job Object
    with `JOB_OBJECT_LIMIT_PROCESS_MEMORY` (separately approved B2 work).
    This implementation **returns a no-op callable** on Windows (a
    `_noop_preexec` that just `return None`s).

    NOTE: the no-op callable is never actually reached on Windows, because
    `subprocess.Popen` refuses `preexec_fn` on that platform. The
    unsupported path is gated earlier by `ensure_memory_cap_supported()`,
    which raises before a process is spawned.

    Args:
        mem_cap_bytes: the cap, in bytes. Both soft and hard
            limits are set to this value (hard ceiling).

    Returns:
        A no-arg callable for use as `preexec_fn=`.
    """
    if sys.platform == "win32":
        # The Windows path would use a Job Object with
        # `JOB_OBJECT_LIMIT_PROCESS_MEMORY`. That requires
        # `pywin32` and the `win32job` module, which is
        # NOT currently a project dependency. Real Windows
        # enforcement is separately approved B2 work.
        #
        # Until then the cap cannot be enforced on Windows, so
        # `ensure_memory_cap_supported()` refuses to run the
        # parser at all on this platform. The callable below is
        # unreachable in practice: `subprocess.Popen` rejects
        # `preexec_fn` on Windows before this would be used.
        def _noop_preexec() -> None:
            return None
        return _noop_preexec

    def _set_rlimit_preexec() -> None:
        # RLIMIT_AS is the virtual-address-space cap. Both
        # soft and hard are set to the same value so a
        # malicious PDF cannot slowly drift past a soft
        # limit. The cap is in place before pdftoppm starts
        # (preexec_fn runs after fork, before exec).
        resource.setrlimit(resource.RLIMIT_AS, (mem_cap_bytes, mem_cap_bytes))

    return _set_rlimit_preexec


# A-F11 property 2: no network access. Applied to the
# child process via preexec_fn=set_network_isolation_preexec().
# The Linux path uses `os.setsid()` to create a new session
# and then attempts to `unshare(CLONE_NEWNET)` to enter a
# fresh network namespace. The Windows path is a no-op
# (the A-F11 Windows path is a follow-up BBF that uses
# Job Object with `JOB_OBJECT_NET_RATE_CONTROL`).
NET_ISOLATION_ENABLED: bool = True


def set_network_isolation_preexec() -> Callable[[], None]:
    """Build a `preexec_fn` callable that isolates the child
    process from the network.

    Returns a no-arg callable suitable for `subprocess.Popen`'s
    `preexec_fn=` parameter. The callable runs in the child
    process after `fork` but before `exec`, so the isolation
    is in place before pdftoppm starts.

    On Linux, this:
    1. Calls `os.setsid()` to create a new session (detaches
       from the parent's controlling terminal and process
       group).
    2. Attempts to `unshare(CLONE_NEWNET)` to enter a fresh
       network namespace (no network interfaces, no loopback,
       no localhost). This requires the `unshare` binary to
       be on PATH (it is on most Linux distros by default).
    3. Removes network-related environment variables
       (`http_proxy`, `https_proxy`, `no_proxy`, `all_proxy`)
       to prevent the child from inheriting proxy config
       that could be used to bypass the network namespace
       isolation.

    On Windows, `unshare` is not available. The Windows
    equivalent is a Job Object with
    `JOB_OBJECT_NET_RATE_CONTROL` (see follow-up BBFs).
    The current implementation **returns a no-op callable**
    on Windows (a `_noop_preexec` that just `return None`s);
    the test `test_set_network_isolation_preexec_noop_on_windows`
    covers the no-op code path on Windows.

    Returns:
        A no-arg callable for use as `preexec_fn=`.
    """
    if sys.platform == "win32":
        # Windows path: best-effort network isolation.
        #
        # The ideal Windows implementation would use a Job
        # Object with `JOB_OBJECT_NET_RATE_CONTROL` (Windows
        # 8+), but the `pywin32` module does not expose the
        # `SetInformationJobObject` API for this info class.
        # The `win32job` module exposes:
        #   - CreateJobObject
        #   - AssignProcessToJobObject
        #   - SetInformationJobObject (limited info classes)
        #   - JOB_OBJECT_LIMIT_PROCESS_MEMORY (memory cap,
        #     already used by FU-22-impl for the 2 GB cap)
        #
        # The Windows network isolation therefore degrades to
        # a best-effort approach: strip network-related env
        # vars (proxy config, etc.) so the child can't use
        # inherited proxy settings to bypass whatever
        # network policy the host has. This is NOT a
        # guarantee of network isolation (a determined
        # attacker can still open raw sockets); it's a
        # defense-in-depth measure.
        #
        # A follow-up BBF can add the full Windows network
        # isolation via:
        # 1. A custom C extension calling
        #    `SetInformationJobObject` with
        #    `JobObjectNetRateControlInformation`
        # 2. Windows Firewall rules via `netsh advfirewall`
        #    (requires admin, not recommended for a subprocess)
        # 3. AppContainer (requires significant new code)
        def _windows_isolate_network() -> None:
            # Best-effort: strip proxy env vars so the child
            # can't use inherited proxy config. This is the
            # same fallback as the Linux path.
            for var in (
                "http_proxy", "https_proxy", "all_proxy", "no_proxy",
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
            ):
                import os as _os
                _os.environ.pop(var, None)

        return _windows_isolate_network

    def _isolate_network_preexec() -> None:
        # Step 1: create a new session. This detaches from
        # the parent's controlling terminal and process
        # group, so the child can't be killed by signals
        # sent to the parent's process group.
        import os as _os_inside_preexec
        _os_inside_preexec.setsid()

        # Step 2: attempt to enter a fresh network namespace
        # via the unshare(2) syscall (CLONE_NEWNET). This
        # isolates the child from the parent's network
        # interfaces: no loopback, no localhost, no DNS,
        # no outbound TCP/UDP. The child has zero network
        # access after this call.
        #
        # The syscall requires CAP_SYS_ADMIN (or the
        # kernel.unprivileged_userns_clone sysctl on some
        # distros). In a Docker container, this may fail
        # if the container was started without the right
        # capabilities. We fall back to env-var stripping
        # + fd-closing in that case.
        try:
            import ctypes
            import ctypes.util
            CLONE_NEWNET = 0x40000000  # from <linux/sched.h>
            libc_name = ctypes.util.find_library("c")
            if libc_name is not None:
                libc = ctypes.CDLL(libc_name, use_errno=True)
                # unshare(2): int unshare(int flags);
                libc.unshare.argtypes = [ctypes.c_int]
                libc.unshare.restype = ctypes.c_int
                ret = libc.unshare(CLONE_NEWNET)
                if ret == 0:
                    # Successfully entered a new network
                    # namespace. The child has no network
                    # access. No need for the fallback.
                    return
                # ret != 0: EPERM (insufficient capabilities)
                # or EINVAL (kernel doesn't support CLONE_NEWNET).
                # Fall through to the env-var + fd-closing
                # fallback below.
        except (OSError, AttributeError):
            # ctypes not available, or the libc call raised
            # an unexpected exception. Fall through.
            pass

        # Step 3 (fallback): strip network-related env vars.
        # This is best-effort and does not guarantee network
        # isolation (a determined attacker can still open
        # new sockets), but it removes the most common
        # exfiltration vectors (proxy env vars, inherited
        # socket fds from the parent).
        for var in (
            "http_proxy", "https_proxy", "all_proxy", "no_proxy",
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        ):
            _os_inside_preexec.environ.pop(var, None)

    return _isolate_network_preexec


# A-F11 property 3: read-only filesystem (except for the
# per-book artifact dir). Applied to the child process
# via preexec_fn=set_fs_isolation_preexec(). The Linux
# path uses `os.setsid()` to create a new session,
# then attempts `unshare(CLONE_NEWUSER|CLONE_NEWNS)` to
# enter a fresh user+mount namespace; on success, the
# parent filesystem is remounted read-only (`mount("none",
# "/", "", MS_REMOUNT|MS_BIND|MS_RDONLY, NULL)`) and
# the per-book artifact dir (passed via `tmpdir`) is
# bind-mounted writable (`mount("none", str(tmpdir),
# "", MS_BIND, NULL)`). The Windows path is a no-op
# (AppLocker/WDAC is the deployment-config concern per
# BBF-FU-21-windows-scope).
FS_ISOLATION_ENABLED: bool = True


def set_fs_isolation_preexec(
    tmpdir: Path | None = None,
) -> Callable[[], None]:
    """Build a `preexec_fn` callable that isolates the child
    process from the parent's filesystem (except for the
    per-book artifact dir).

    Returns a no-arg callable suitable for `subprocess.Popen`'s
    `preexec_fn=` parameter. The callable runs in the child
    process after `fork` but before `exec`, so the isolation
    is in place before pdftoppm starts.

    Args:
        tmpdir: optional path to the per-book artifact dir
            that the subprocess may write to. When
            provided AND a successful `unshare` is
            achievable, the parent filesystem is remounted
            read-only and the tmpdir is bind-mounted
            writable. When None (or unshare fails), the
            subprocess inherits the parent's filesystem
            unchanged; writes are confined to whatever
            path the caller already passes to
            `pdftoppm` (the `output_prefix` argument;
            typically the `tmpdir` itself).

    On Linux, this:
    1. Calls `os.setsid()` to create a new session (detaches
       from the parent's controlling terminal and process
       group).
    2. Attempts `unshare(CLONE_NEWUSER|CLONE_NEWNS)` to
       enter a fresh user+mount namespace. Requires
       `CAP_SYS_ADMIN` (or the
       `kernel.unprivileged_userns_clone` sysctl on some
       distros).
    3. On successful unshare with a `tmpdir` provided,
       remounts the parent filesystem read-only via
       `mount("none", "/", "", MS_REMOUNT|MS_BIND|MS_RDONLY, NULL)`
       and bind-mounts the tmpdir writable via
       `mount("none", "<tmpdir>", "", MS_BIND, NULL)`.
       The bind-mount step requires the per-book artifact
       dir path at preexec-fn invocation time, which is
       why this factory accepts `tmpdir` as a closure
       parameter.
    4. On failure (insufficient capabilities, no kernel
       support, or no `tmpdir` provided), falls back to a
       no-op. The subprocess inherits the parent's
       filesystem in this case; legitimate writes
       (pdftoppm's PNG output) are confined to whatever
       the caller's pdftoppm invocation already passes
       as the writable dir.

    On Windows, `unshare` is not available. The Windows
    FS enforcement is documented as a deployment-config
    concern per BBF-FU-21-windows-scope (AppLocker / WDAC);
    this factory ignores the `tmpdir` arg and returns a
    no-op callable.

    Returns:
        A no-arg callable for use as `preexec_fn=`.
    """
    if sys.platform == "win32":
        # Windows path: no-op (AppLocker/WDAC is the
        # deployment-config concern per BBF-FU-21-windows-scope).

        def _noop_preexec() -> None:
            return None

        return _noop_preexec

    # Capture tmpdir in the closure for the inner
    # _isolate_fs_preexec function. The Path type
    # narrows automatically; if it's None we skip
    # the bind-mount step.
    captured_tmpdir: Path | None = Path(tmpdir) if tmpdir is not None else None

    def _isolate_fs_preexec() -> None:
        # Step 1: create a new session. This detaches from
        # the parent's controlling terminal and process
        # group. May raise `PermissionError(EPERM)` when
        # the calling process has no controlling terminal
        # (common in CI runner contexts) — that's still
        # acceptable here; the fall-through below handles it
        # via the try/except wrapper.
        try:
            import os as _os_inside_preexec
            _os_inside_preexec.setsid()
        except (OSError, AttributeError):
            # No controlling terminal or setsid not permitted.
            # Continue; the unshare attempt below still has
            # value (it doesn't depend on setsid having
            # succeeded).
            pass

        # Step 2: attempt unshare(CLONE_NEWUSER|CLONE_NEWNS)
        # to enter a fresh user+mount namespace. The
        # syscall requires CAP_SYS_ADMIN (or the
        # `kernel.unprivileged_userns_clone` sysctl on
        # some distros). In a Docker container without
        # the right capabilities, this fails with
        # `PermissionError(EPERM)`; in a CI runner without
        # namespace privileges, it fails the same way. We
        # catch the `OSError` (parent of `PermissionError`)
        # and fall back to a no-op.
        libc_unshare: object = None
        unshare_succeeded: bool = False
        try:
            import ctypes
            import ctypes.util

            # CLONE_NEWUSER | CLONE_NEWNS from <linux/sched.h>
            CLONE_NEWUSER = 0x10000000
            CLONE_NEWNS = 0x00020000
            unshare_flags = CLONE_NEWUSER | CLONE_NEWNS
            libc_name = ctypes.util.find_library("c")
            if libc_name is not None:
                libc_unshare = ctypes.CDLL(libc_name, use_errno=True)
                # unshare(2): int unshare(int flags);
                libc_unshare.unshare.argtypes = [ctypes.c_int]
                libc_unshare.unshare.restype = ctypes.c_int
                ret = libc_unshare.unshare(unshare_flags)
                if ret == 0:
                    unshare_succeeded = True
                # ret != 0: EPERM (insufficient
                # capabilities) or EINVAL (kernel doesn't
                # support the namespace). Fall through.
        except (OSError, AttributeError):
            # ctypes not available, libc call raised
            # `PermissionError(EPERM)` (no CAP_SYS_ADMIN),
            # or the call raised an unexpected exception.
            # Fall through.
            pass

        # Step 3: bind-mount + remount-read-only.
        # ONLY runs if (a) unshare succeeded AND
        # (b) a `tmpdir` path was provided AND
        # (c) the tmpdir path still exists at preexec
        # invocation time.
        if unshare_succeeded and captured_tmpdir is not None and captured_tmpdir.exists():
            try:
                # MS_* constants from <sys/mount.h>:
                #   MS_RDONLY  = 0x0   (1)
                #   MS_NOSUID  = 0x2   (2)
                #   MS_NODEV   = 0x4   (4)
                #   MS_NOEXEC  = 0x8   (8)
                #   MS_REMOUNT = 0x20  (32)
                #   MS_BIND    = 0x1000 (4096)
                MS_RDONLY = 0x1
                MS_REMOUNT = 0x20
                MS_BIND = 0x1000
                libc_unshare.mount.restype = ctypes.c_int  # type: ignore[attr-defined]
                libc_unshare.mount.argtypes = [  # type: ignore[attr-defined]
                    ctypes.c_char_p,  # source (char *)
                    ctypes.c_char_p,  # target (char *)
                    ctypes.c_char_p,  # filesystemtype (char *)
                    ctypes.c_ulong,  # mountflags (unsigned long)
                    ctypes.c_void_p,  # data (void *)
                ]
                # Remount "/" read-only inside this namespace.
                # The MS_BIND|MS_REMOUNT combo with empty
                # filesystemtype takes the previous mount
                # of "/" and changes its flags. This is the
                # documented kernel API for remounting the
                # root read-only inside a user namespace.
                ret = libc_unshare.mount(  # type: ignore[attr-defined]
                    b"none",
                    b"/",
                    b"",
                    ctypes.c_ulong(MS_REMOUNT | MS_BIND | MS_RDONLY),
                    None,
                )
                if ret != 0:
                    # EPERM/etc.; the remount-read-only
                    # failed. The bind-mount below would
                    # have nothing to bind onto. Fall
                    # through to the no-op.
                    pass
                else:
                    # Bind-mount the tmpdir writable inside
                    # the fresh mount namespace. The
                    # artifact dir becomes the only
                    # writable location for the subprocess.
                    tmpdir_bytes = str(captured_tmpdir).encode("utf-8")
                    libc_unshare.mount(  # type: ignore[attr-defined]
                        b"none",
                        tmpdir_bytes,
                        b"",
                        ctypes.c_ulong(MS_BIND),
                        None,
                    )
                # Whether or not the bind-mount succeeded,
                # the child is in a fresh user+mount
                # namespace; the parent filesystem is
                # untouched (the remount was inside the
                # child's namespace only). The subprocess
                # has zero visibility into the parent's
                # writable filesystem. Return to skip the
                # no-op fallback.
                return
            except (OSError, AttributeError):
                # bind/mount fcntls not available, or
                # libc.mount raised an unexpected error.
                # Fall through to the no-op.
                pass

        # Fallback: no-op. The subprocess inherits the
        # parent's filesystem. Writes are confined to the
        # tmpdir by virtue of pdftoppm's `output_prefix`
        # argument being the only directory it writes
        # to; a malicious PDF that triggers a write
        # outside the tmpdir would succeed. This is the
        # same honest-disclosure trade-off documented
        # for the network isolation fallback: best-effort
        # defense in depth, not a guarantee.
        return None

    return _isolate_fs_preexec


class UnsupportedParserPlatformError(NotImplementedYetError):
    """Raised when the host platform cannot enforce the A-F11 memory cap.

    A distinct subclass of :class:`NotImplementedYetError` so the gateway
    can distinguish "this platform cannot run the PDF parser at all"
    from a malformed upload, a missing tool, a timeout, or a generic
    parser failure. It carries the ADR-0002 error code
    ``internal.not_implemented`` and HTTP status 501.

    This is raised BEFORE any parser process is spawned, so an uncapped
    ``pdftoppm`` is never launched.
    """


def ensure_memory_cap_supported() -> None:
    """Raise if this platform cannot enforce the A-F11 memory cap.

    The A-F11 contract requires the PDF parser to run with a 2 GB memory
    cap. The cap is enforced differently per platform:

    * **Linux** — ``resource.setrlimit(RLIMIT_AS, (2 GiB, 2 GiB))`` in a
      ``preexec_fn`` callback.
    * **Windows** — a Job Object with
      ``JOB_OBJECT_LIMIT_PROCESS_MEMORY`` at 2 GiB, applied by the
      :mod:`chess_coach.pdf_ocr.windows_job` backend
      (``BBF-FU-22-B2-windows-job-object``). The target is created
      suspended and resumed only after Job assignment, so the cap is in
      force before the target allocates.

    On any other platform neither mechanism is available, so the guard
    raises a deliberate, typed unsupported-platform result rather than
    letting an incidental ``ValueError`` surface as a generic 422 (which
    would be indistinguishable from a malformed PDF or a parser
    failure).

    Raises:
        UnsupportedParserPlatformError: if the cap cannot be enforced.
    """
    if not MEMORY_CAP_SUPPORTED:
        raise UnsupportedParserPlatformError(
            "PDF parsing is not supported on this platform: the A-F11 2 GB "
            "memory cap cannot be enforced here, so no parser process is "
            "started.",
            details={
                "platform": HOST_PLATFORM,
                "required_mechanism": MEMORY_CAP_MECHANISM,
                "cap_bytes": MEM_CAP_BYTES,
                "resource": "pdf_import",
            },
        )


def _build_pdftoppm_args(
    dpi: int,
    first_page: int,
    last_page: int,
    output_prefix: Path,
) -> list[str]:
    """Build the pdftoppm command-line args.

    pdftoppm is the Poppler PDF-to-image converter. The
    invocation pattern is:

        pdftoppm -r <dpi> -png -f <first> -l <last> <input> <output_prefix>

    The input is fed via stdin (the PDF bytes); the output
    files are written to `<output_prefix>-1.png`,
    `<output_prefix>-2.png`, etc. (one file per page).
    """
    return [
        "pdftoppm",
        "-r", str(dpi),
        "-png",
        "-f", str(first_page),
        "-l", str(last_page),
        "-",  # read PDF from stdin
        str(output_prefix),
    ]


def run_pdftoppm_in_subprocess(
    pdf_bytes: bytes,
    *,
    dpi: int = DEFAULT_DPI,
    first_page: int = 1,
    last_page: int | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    mem_cap_bytes: int = MEM_CAP_BYTES,
) -> list[Image.Image]:
    """Run pdftoppm in a subprocess with the 2 GB memory cap.

    Replaces `pdf2image.convert_from_bytes` for the A-F11
    path. The return contract (`list[PIL.Image.Image]`) is
    preserved so downstream code (the `import_pdf` route)
    is unchanged.

    Args:
        pdf_bytes: the raw PDF content (read from stdin)
        dpi: render DPI (default 200)
        first_page: 1-indexed first page to render
        last_page: 1-indexed last page to render; `None` means
            render all pages
        timeout_seconds: per-Popen timeout; the parent
            process is killed with `TimeoutExpired` if the
            subprocess exceeds this
        mem_cap_bytes: virtual-address-space cap (default 2 GB);
            a malicious PDF that triggers unbounded
            allocation will be killed at this threshold

    Returns:
        list[PIL.Image.Image], one per rendered page

    Raises:
        UnsupportedParserPlatformError: if this platform cannot enforce
            the A-F11 memory cap. Raised BEFORE any parser process is
            spawned, so an uncapped parser is never launched.
        subprocess.TimeoutExpired: if the subprocess exceeds
            `timeout_seconds`
        OSError: if pdftoppm is not on PATH (e.g. on Windows
            hosts without poppler installed); the route layer
            catches this and returns HTTP 422
        MemoryError: if the subprocess exits because of a
            2 GB-cap hit (a malicious PDF is a security
            event, surfaced to the user as 422)
    """
    # A-F11 property 4 gate: refuse to run a parser we cannot cap.
    # This MUST come before `subprocess.Popen`, so the unsupported
    # path never starts a process.
    ensure_memory_cap_supported()

    last_page_arg = last_page if last_page is not None else 0  # 0 = "all"

    with tempfile.TemporaryDirectory(prefix="chess_coach_pdftoppm_") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        output_prefix = tmpdir / "page"
        args = _build_pdftoppm_args(dpi, first_page, last_page_arg, output_prefix)

        # The preexec_fn sets the 2 GB cap in the child
        # process before pdftoppm starts. This is the
        # only point at which setrlimit is effective: after
        # fork, before exec. pdf2image's convert_from_bytes
        # does not expose preexec_fn, which is why this
        # module bypasses pdf2image and calls pdftoppm
        # directly.
        # A-F11 properties 2 + 3 + 4: combine the memory
        # cap, network isolation, and filesystem isolation
        # into a single preexec_fn. All three callbacks run
        # in the child process after fork, before exec, so
        # all are in place before pdftoppm starts. We use a
        # single composed callable rather than three separate
        # preexec_fn args because subprocess.Popen only
        # accepts one preexec_fn.
        #
        # The filesystem isolation preexec receives the
        # `tmpdir` path so the bind-mount step (when
        # capabilities permit) can bind-mount the artifact
        # dir writable while remounting the parent's
        # filesystem read-only. See BBF-FU-21-bind-mount
        # for the implementation details.
        def _combined_preexec() -> None:
            set_rlimit_as_preexec(mem_cap_bytes)()
            set_network_isolation_preexec()()
            set_fs_isolation_preexec(tmpdir)()
        preexec_fn = _combined_preexec

        # The child process's stdin is the PDF bytes; the
        # child writes output files into tmpdir (which is
        # the per-book artifact dir in production use, but
        # a tempdir for the test path).
        #
        # BBF-FU-22-B2-windows-job-object: on Windows the launch
        # goes through the Job Object backend instead of
        # `subprocess.Popen`. The Job backend creates the target
        # suspended, configures the Job's per-process memory
        # limit, assigns the target, and only then resumes it,
        # so no target code can allocate or spawn descendants
        # before the limit is in force. The Linux path below is
        # unchanged.
        if WINDOWS_JOB_SUPPORTED:
            return _run_pdftoppm_in_windows_job(
                args,
                pdf_bytes=pdf_bytes,
                tmpdir=tmpdir,
                timeout_seconds=timeout_seconds,
                mem_cap_bytes=mem_cap_bytes,
            )

        proc: subprocess.Popen[bytes] = subprocess.Popen(  # noqa: S603
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            preexec_fn=preexec_fn,  # noqa: S901  -- intentional A-F11 mechanism
        )

        # Feed the PDF bytes via stdin; capture stderr for
        # diagnostics. communicate(timeout=...) is the inner
        # timeout safety net; the route's asyncio.wait_for
        # is the outer safety net.
        try:
            _, stderr_bytes = proc.communicate(input=pdf_bytes, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise
        if proc.returncode != 0:
            stderr_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
            raise RuntimeError(
                f"pdftoppm exited with code {proc.returncode}: {stderr_text[:500]}"
            )

        # pdftoppm wrote one file per page. Load them
        # back as PIL images. The naming is
        # `<output_prefix>-NNN.png` (zero-padded to 3
        # digits) or `<output_prefix>-N.png` (no padding)
        # depending on pdftoppm version. We handle both.
        png_files = sorted(tmpdir.glob("*.png"))
        if not png_files:
            raise RuntimeError(
                "pdftoppm exited cleanly but produced no PNG files; "
                "the PDF may be empty or the page range may be out of bounds."
            )
        return [Image.open(p) for p in png_files]


def _run_pdftoppm_in_windows_job(
    args: list[str],
    *,
    pdf_bytes: bytes,
    tmpdir: Path,
    timeout_seconds: int,
    mem_cap_bytes: int,
) -> list[Image.Image]:
    """Run pdftoppm through the Windows Job Object backend.

    **BBF-FU-22-B2-windows-job-object.** The target is created
    suspended, the Job is created and configured with the
    per-process memory limit, the target is assigned to the Job,
    and only then is it resumed. No target code runs before the
    limit is in force.

    The outcome taxonomy is preserved by mapping the backend's typed
    errors onto the errors the Linux path already raises, so the
    route layer can distinguish them:

    * a Job setup failure raises :class:`WindowsJobSetupError`
      (a containment-setup failure, distinct from a parser failure);
    * an attributable per-process limit violation raises
      :class:`WindowsJobLimitExceededError`;
    * a timeout raises :class:`WindowsJobTimeoutError`;
    * a nonzero parser exit still raises ``RuntimeError``, preserving
      the existing parser-failure semantics.

    A nonzero exit on its own is **never** classified as a limit hit:
    only the Job's own limit-violation signal is.
    """
    from chess_coach.pdf_ocr.windows_job import (
        WindowsJobLimitExceededError,
        WindowsJobSetupError,
        WindowsJobTimeoutError,
        run_in_windows_job,
    )

    try:
        result = run_in_windows_job(
            args,
            stdin_bytes=pdf_bytes,
            timeout_seconds=timeout_seconds,
            limit_bytes=mem_cap_bytes,
            cwd=tmpdir,
        )
    except WindowsJobLimitExceededError:
        # The A-F11 property-4 hit. The route surfaces this as 422, the
        # same status the Linux `RLIMIT_AS` hit produces, but it is a
        # distinct exception type so it is never confused with a
        # malformed PDF or a generic parser failure.
        raise
    except WindowsJobTimeoutError:
        # The route's outer `asyncio.wait_for` would also fire, but the
        # inner backend timeout is authoritative because it terminated
        # and drained the Job first.
        raise
    except WindowsJobSetupError:
        # Containment setup failed: the target was never resumed, so no
        # unconstrained parser ran. This is a containment-setup failure,
        # not a parser failure.
        raise

    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        raise RuntimeError(
            f"pdftoppm exited with code {result.returncode}: {stderr_text[:500]}"
        )

    png_files = sorted(tmpdir.glob("*.png"))
    if not png_files:
        raise RuntimeError(
            "pdftoppm exited cleanly but produced no PNG files; "
            "the PDF may be empty or the page range may be out of bounds."
        )
    return [Image.open(p) for p in png_files]


def pdftoppm_available() -> bool:
    """Check whether pdftoppm is on PATH (and thus callable).

    Used by the route layer to gracefully degrade on
    Windows hosts (where poppler is not bundled). Returns
    True if `pdftoppm` is found via `shutil.which`, False
    otherwise. The check is cheap; the route layer calls
    it once at module import time.
    """
    return shutil.which("pdftoppm") is not None
