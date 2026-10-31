"""A-F11 subprocess runner — wraps pdftoppm with sandbox primitives.

This module provides a subprocess-based replacement for
`pdf2image.convert_from_bytes` that exposes the
`subprocess.Popen` parameters pdf2image does not (notably
`preexec_fn` for setting resource limits in the child
process). Per `docs/08_security/security-strategy.md`
§A-F11, the PDF parser MUST run in an isolated subprocess
with no network access, read-only filesystem, 2 GB memory
cap, and a 5-minute timeout.

**The 2 GB memory cap** was first implemented (FU-22-impl) via
`resource.setrlimit(RLIMIT_AS)` in a `preexec_fn` callback.

**BBF-FU-20-linux-phase1-network-isolation replaced the composed
`preexec_fn` approach on Linux.** The Linux launch now goes through the
combined sandbox launcher in :mod:`chess_coach.pdf_ocr.linux_sandbox`,
which owns ONE namespace lifecycle
(`CLONE_NEWUSER | CLONE_NEWNET | CLONE_NEWNS`) and applies the A-F11
network, filesystem, descriptor, and memory policy transactionally
*before* the parser is executed. There is no proxy-stripping fallback, no
filesystem no-op fallback, and no unconstrained fallback: every setup
stage fails closed. The timeout is still enforced by the route's
`asyncio.wait_for` wrapper and by the launcher's own budget.

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

import contextlib
import os
import shutil
import subprocess  # noqa: S404  -- intentional: PDF parsing requires subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from chess_coach.errors import NotImplementedYetError
from chess_coach.pdf_ocr.linux_sandbox import (
    STATUS_FD,
    STATUS_OK,
    STATUS_SETUP_FAILURE,
    NetworkIsolationSetupError,
    build_launcher_argv,
)
from chess_coach.pdf_ocr.windows_job import WINDOWS_JOB_SUPPORTED

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

#: The capability that enforces the memory cap, named for the error details.
MEMORY_CAP_MECHANISM: str = (
    "RLIMIT_AS in the sandbox launcher"
    if HOST_PLATFORM != "win32"
    else "Windows Job Object (JOB_OBJECT_LIMIT_PROCESS_MEMORY)"
)

#: True when this platform can enforce the A-F11 property-2 network
#: isolation requirement.
#:
#: **Linux:** the cap is enforced by the combined sandbox launcher in
#: :mod:`chess_coach.pdf_ocr.linux_sandbox`, which owns one
#: ``CLONE_NEWUSER | CLONE_NEWNET | CLONE_NEWNS`` namespace lifecycle and
#: applies the network, filesystem, descriptor, and memory policy
#: transactionally before the parser is executed
#: (``BBF-FU-20-linux-phase1-network-isolation``).
#:
#: **Windows:** NO network-isolation boundary is proven. The Job Object
#: backend enforces the *memory* cap, not network isolation, and Job Object
#: network-rate control is throttling, never isolation. Proxy-environment
#: stripping is defense in depth, never isolation. Windows PDF parsing is
#: therefore explicitly unsupported until a separately proven
#: process-scoped or deployment-scoped no-network boundary exists.
NETWORK_ISOLATION_SUPPORTED: bool = HOST_PLATFORM != "win32"

#: The capability that enforces the network isolation, named for the error
#: details.
NETWORK_ISOLATION_MECHANISM: str = (
    "Linux user+network namespace (CLONE_NEWUSER|CLONE_NEWNET|CLONE_NEWNS)"
    if HOST_PLATFORM != "win32"
    else "none (no proven Windows network-isolation boundary)"
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


class NetworkIsolationUnsupportedError(NotImplementedYetError):
    """Raised when the host platform cannot enforce A-F11 network isolation.

    A distinct subclass of :class:`NotImplementedYetError` so the gateway
    can distinguish "this platform has no proven network-isolation
    boundary" from a malformed upload, a missing tool, a timeout, a
    memory-limit hit, and a Linux namespace setup failure. It carries the
    ADR-0002 error code ``internal.not_implemented`` and HTTP status 501.

    This is raised BEFORE any parser process or Job Object target is
    created, so no parser is ever launched on a platform whose network
    isolation is not enforced.

    **BBF-FU-20-linux-phase1-network-isolation.** Windows PDF parsing is
    explicitly unsupported: the Job Object backend enforces the *memory*
    cap, not network isolation, and Job Object network-rate control is
    throttling rather than isolation. Proxy-environment stripping is
    defense in depth, never isolation.
    """


def ensure_network_isolation_supported() -> None:
    """Raise if this platform cannot enforce the A-F11 network isolation.

    The A-F11 contract requires the PDF parser to run with **no network
    access**. The requirement is enforced differently per platform:

    * **Linux** -- the combined sandbox launcher in
      :mod:`chess_coach.pdf_ocr.linux_sandbox` enters a fresh
      ``CLONE_NEWUSER | CLONE_NEWNET | CLONE_NEWNS`` namespace before the
      parser is executed, so the parser has no usable interface, no
      loopback, no DNS, and no outbound TCP/UDP.
    * **Windows** -- there is no proven no-network boundary. The Job
      Object backend enforces the memory cap only. Until AppContainer (or
      an explicitly accepted deployment-level boundary) is separately
      validated, Windows PDF parsing is refused.

    Raises:
        NetworkIsolationUnsupportedError: if no network-isolation boundary
            is available. Raised BEFORE any parser process or Job target
            is created.
    """
    if not NETWORK_ISOLATION_SUPPORTED:
        raise NetworkIsolationUnsupportedError(
            "PDF parsing is not supported on this platform: the A-F11 "
            "no-network requirement cannot be enforced here, so no parser "
            "process is started.",
            details={
                "platform": HOST_PLATFORM,
                "required_mechanism": NETWORK_ISOLATION_MECHANISM,
                "resource": "pdf_import",
            },
        )


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


def _read_status_line(status_fd: int, proc: subprocess.Popen[bytes]) -> str | None:
    """Read the launcher's status line from the dedicated status pipe.

    Returns the first line the launcher wrote, or ``None`` if the launcher
    wrote nothing (which means it died before reporting a stage). The
    status pipe is separate from the parser's stderr so a setup failure is
    never confused with parser output.
    """
    import select

    try:
        readable, _, _ = select.select([status_fd], [], [], 10.0)
    except (OSError, ValueError):
        return None
    if not readable:
        return None
    try:
        data = os.read(status_fd, 4096)
    except OSError:
        return None
    if not data:
        return None
    first = data.decode("utf-8", errors="replace").splitlines()
    return first[0] if first else None


def _kill_launcher(proc: subprocess.Popen[bytes]) -> None:
    """Terminate the launcher and its parser process group, then drain it.

    The launcher starts a new session, so its process group contains only
    the launcher and the parser it execs. Killing the group is therefore
    scoped and never reaches an unrelated process.
    """
    signalled = False
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(proc.pid, 15)
        signalled = True
    if not signalled:
        with contextlib.suppress(ProcessLookupError, OSError):
            proc.kill()
        return
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.killpg(proc.pid, 9)
        with contextlib.suppress(ProcessLookupError, OSError):
            proc.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)


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

    # A-F11 property 2 gate: refuse to run a parser we cannot isolate
    # from the network. This MUST come before the Job backend is invoked
    # and before any process is created, so on a platform with no proven
    # no-network boundary no parser and no Job target is ever created.
    #
    # **BBF-FU-20-linux-phase1-network-isolation.** On Windows this is the
    # refusal path: the Job Object backend enforces the memory cap, not
    # network isolation.
    ensure_network_isolation_supported()

    last_page_arg = last_page if last_page is not None else 0  # 0 = "all"

    with tempfile.TemporaryDirectory(prefix="chess_coach_pdftoppm_") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        output_prefix = tmpdir / "page"
        args = _build_pdftoppm_args(dpi, first_page, last_page_arg, output_prefix)

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
        # before the limit is in force.
        #
        # BBF-FU-20-linux-phase1-network-isolation: the Linux path goes
        # through the combined sandbox launcher instead of a composed
        # `preexec_fn`. The launcher owns ONE namespace lifecycle
        # (CLONE_NEWUSER|CLONE_NEWNET|CLONE_NEWNS) and applies the
        # network, filesystem, descriptor, and memory policy
        # transactionally before it execs pdftoppm, so there is one
        # namespace owner, one setsid(), and no fallback.
        if WINDOWS_JOB_SUPPORTED:
            return _run_pdftoppm_in_windows_job(
                args,
                pdf_bytes=pdf_bytes,
                tmpdir=tmpdir,
                timeout_seconds=timeout_seconds,
                mem_cap_bytes=mem_cap_bytes,
            )

        # --- Linux: the combined sandbox launcher ---
        #
        # The launcher is a separate program invoked with a controlled
        # argv protocol (no shell string is ever evaluated). It reports
        # "OK" on a dedicated status descriptor only after EVERY
        # containment stage has succeeded, and only then execs pdftoppm.
        # A setup failure is reported as
        # "SETUP_FAILURE <stage>\x00<message>" and the parser is never
        # executed.
        status_r, status_w = os.pipe()
        launcher_argv = build_launcher_argv(
            args,
            artifact_dir=tmpdir,
            limit_bytes=mem_cap_bytes,
            status_fd=STATUS_FD,
        )
        try:
            proc = subprocess.Popen(  # noqa: S603
                launcher_argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                pass_fds=(status_w,),
                start_new_session=True,
            )
        except OSError:
            os.close(status_r)
            os.close(status_w)
            raise

        # The launcher writes to status_w (inherited as STATUS_FD); the
        # parent's own copy is closed so only the child holds it.
        os.close(status_w)
        try:
            status_line = _read_status_line(status_r, proc)
        finally:
            os.close(status_r)

        if status_line is not None and not status_line.startswith(STATUS_OK):
            _kill_launcher(proc)
            stage, _, message = status_line.partition("\x00")
            stage = stage.removeprefix(f"{STATUS_SETUP_FAILURE} ").strip()
            raise NetworkIsolationSetupError(
                message or "the sandbox setup failed",
                stage=stage or "unknown",
                details={"launcher": "linux_sandbox"},
            )

        # Feed the PDF bytes via stdin; capture stderr for
        # diagnostics. communicate(timeout=...) is the inner
        # timeout safety net; the route's asyncio.wait_for
        # is the outer safety net.
        try:
            _, stderr_bytes = proc.communicate(input=pdf_bytes, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            _kill_launcher(proc)
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
