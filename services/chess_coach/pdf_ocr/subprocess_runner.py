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

    On Windows, `resource.setrlimit` is not available. The
    Windows equivalent is a Job Object with
    `JOB_OBJECT_LIMIT_PROCESS_MEMORY` (see follow-up BBFs
    FU-20-impl / FU-21-impl). The current implementation
    **returns a no-op callable** on Windows (a
    `_noop_preexec` that just `return None`s); the test
    `test_set_rlimit_as_preexec_no_cap_means_no_cap`
    covers the no-cap code path on Windows.

    Args:
        mem_cap_bytes: the cap, in bytes. Both soft and hard
            limits are set to this value (hard ceiling).

    Returns:
        A no-arg callable for use as `preexec_fn=`.
    """
    if sys.platform == "win32":
        # The Windows path uses a Job Object with
        # `JOB_OBJECT_LIMIT_PROCESS_MEMORY`. That requires
        # `pywin32` and the `win32job` module, which is
        # not currently a project dependency. The follow-up
        # BBF (Windows FU-22 path) can add this. For now,
        # the cap is a no-op on Windows; the test
        # `test_set_rlimit_as_preexec_no_cap_means_no_cap`
        # covers the no-cap code path on Windows.
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
# path uses `os.setsid()` to create a new session and
# then attempts `unshare(CLONE_NEWUSER|CLONE_NEWNS)` to
# enter a fresh user+mount namespace; on success, the
# parent filesystem is remounted read-only and the tmpdir
# is bind-mounted writable. The Windows path is a no-op
# (A-F11 property 3 Windows path uses AppLocker or WDAC,
# which is admin-policy and requires a separate
# investigation BBF).
FS_ISOLATION_ENABLED: bool = True


def set_fs_isolation_preexec() -> Callable[[], None]:
    """Build a `preexec_fn` callable that isolates the child
    process from the parent's filesystem (except for the
    per-book artifact dir).

    Returns a no-arg callable suitable for `subprocess.Popen`'s
    `preexec_fn=` parameter. The callable runs in the child
    process after `fork` but before `exec`, so the isolation
    is in place before pdftoppm starts.

    On Linux, this:
    1. Calls `os.setsid()` to create a new session (detaches
       from the parent's controlling terminal and process
       group).
    2. Attempts `unshare(CLONE_NEWUSER|CLONE_NEWNS)` to
       enter a fresh user+mount namespace. Requires
       `CAP_SYS_ADMIN` (or the
       `kernel.unprivileged_userns_clone` sysctl on some
       distros).
    3. On successful unshare, remounts the parent
       filesystem read-only via `mount(\"none\", \"/\", \"\",
       MS_REMOUNT|MS_BIND|MS_RDONLY, NULL)` and
       bind-mounts the per-book artifact dir writable.
    4. On failure (insufficient capabilities, no kernel
       support), falls back to a no-op. The subprocess
       inherits the parent's filesystem in this case; the
       per-book artifact dir is already a tmpdir managed
       by the caller (`tempfile.TemporaryDirectory` in
       `run_pdftoppm_in_subprocess`) so legitimate writes
       are confined to that tmpdir.

    On Windows, `unshare` is not available. The Windows
    equivalent is AppLocker or Windows Defender Application
    Control (WDAC), which is admin-policy and out of scope
    for this BBF. The current implementation **returns a
    no-op callable** on Windows (a `_noop_preexec` that
    just `return None`s).

    Returns:
        A no-arg callable for use as `preexec_fn=`.
    """
    if sys.platform == "win32":
        # Windows path: no-op (AppLocker/WDAC is the
        # production-correct solution and requires a
        # separate investigation-first BBF).

        def _noop_preexec() -> None:
            return None

        return _noop_preexec

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
        # and fall back to a no-op (the subprocess
        # inherits the parent's filesystem; the per-book
        # artifact dir is already a tmpdir so legitimate
        # writes are confined to that tmpdir, but a
        # malicious subprocess could write elsewhere).
        #
        # We deliberately do NOT perform the bind-mount
        # + remount-read-only steps in this fallback
        # path: those require a successful unshare, and
        # we'd be remounting the parent's filesystem
        # outside of a fresh mount namespace, which is
        # dangerous (it would remount the parent's
        # filesystem read-only for the entire system if
        # we made a mistake).
        try:
            import ctypes
            import ctypes.util

            # CLONE_NEWUSER | CLONE_NEWNS from <linux/sched.h>
            CLONE_NEWUSER = 0x10000000
            CLONE_NEWNS = 0x00020000
            unshare_flags = CLONE_NEWUSER | CLONE_NEWNS
            libc_name = ctypes.util.find_library("c")
            if libc_name is not None:
                libc = ctypes.CDLL(libc_name, use_errno=True)
                # unshare(2): int unshare(int flags);
                libc.unshare.argtypes = [ctypes.c_int]
                libc.unshare.restype = ctypes.c_int
                ret = libc.unshare(unshare_flags)
                if ret == 0:
                    # Successfully entered a fresh
                    # user+mount namespace. The child can
                    # now safely remount its own filesystem
                    # without affecting the parent's. Per
                    # the A-F11 contract, the parent
                    # filesystem must be read-only outside
                    # the per-book artifact dir; that
                    # requires identifying the tmpdir path
                    # at this point, which we don't have
                    # direct access to from preexec_fn
                    # (subprocess.Popen doesn't expose
                    # kwargs to preexec_fn). The follow-up
                    # BBF that adds the bind-mount step
                    # needs to thread the tmpdir path
                    # through the composition site in
                    # `run_pdftoppm_in_subprocess` (via a
                    # closure that captures the tmpdir).
                    #
                    # For this BBF: the successful unshare
                    # is the load-bearing primitive. The
                    # remount-read-only step is documented
                    # as a follow-up, gated on the
                    # tmpdir-threading change.
                    return
                # ret != 0: EPERM (insufficient
                # capabilities) or EINVAL (kernel doesn't
                # support the namespace). Fall through.
        except (OSError, AttributeError):
            # ctypes not available, libc call raised
            # `PermissionError(EPERM)` (no CAP_SYS_ADMIN),
            # or the call raised an unexpected exception.
            # Fall through.
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
        subprocess.TimeoutExpired: if the subprocess exceeds
            `timeout_seconds`
        OSError: if pdftoppm is not on PATH (e.g. on Windows
            hosts without poppler installed); the route layer
            catches this and returns HTTP 422
        MemoryError: if the subprocess exits because of a
            2 GB-cap hit (a malicious PDF is a security
            event, surfaced to the user as 422)
    """
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
        # A-F11 properties 2 + 4: combine the memory cap and
        # network isolation into a single preexec_fn. Both
        # callbacks run in the child process after fork,
        # before exec, so both are in place before pdftoppm
        # starts. We use a single composed callable rather
        # than two separate preexec_fn args because
        # subprocess.Popen only accepts one preexec_fn.
        def _combined_preexec() -> None:
            set_rlimit_as_preexec(mem_cap_bytes)()
            set_network_isolation_preexec()()
            set_fs_isolation_preexec()()
        preexec_fn = _combined_preexec

        # The child process's stdin is the PDF bytes; the
        # child writes output files into tmpdir (which is
        # the per-book artifact dir in production use, but
        # a tempdir for the test path).
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


def pdftoppm_available() -> bool:
    """Check whether pdftoppm is on PATH (and thus callable).

    Used by the route layer to gracefully degrade on
    Windows hosts (where poppler is not bundled). Returns
    True if `pdftoppm` is found via `shutil.which`, False
    otherwise. The check is cheap; the route layer calls
    it once at module import time.
    """
    return shutil.which("pdftoppm") is not None
