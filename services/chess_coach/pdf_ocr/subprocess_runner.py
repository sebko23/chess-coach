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
import io
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

#: Environment variable that opts the Windows host into the AppContainer
#: network-isolation backend.
#:
#: The backend is **off by default** so that the shipped Windows behaviour
#: is unchanged until the enablement contract is explicitly reviewed. With
#: it off, Windows PDF parsing keeps raising the 501
#: ``internal.not_implemented`` refusal. With it on, the Windows parser
#: path runs inside an AppContainer with zero network capabilities.
#:
#: Why an env var and not a ``GatewaySettings`` field: the flag selects a
#: containment mechanism, not a deployment setting, and the PDF OCR module
#: is imported by the shared runner independently of the gateway. The
#: same pattern is used by ``CHESS_COACH_OCR_BACKEND``.
ENV_WINDOWS_APPCONTAINER = "CHESS_COACH_WINDOWS_APPCONTAINER"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def windows_appcontainer_is_enabled() -> bool:
    """Whether the Windows AppContainer isolation backend is opted in.

    Read at call time rather than import time so the flag can be set per
    process by a deployment or a test without re-importing the module.
    """
    if HOST_PLATFORM != "win32":
        return False
    return (os.getenv(ENV_WINDOWS_APPCONTAINER) or "").strip().lower() in _TRUTHY

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
#: **Windows:** the AppContainer backend in
#: :mod:`chess_coach.pdf_ocr.windows_appcontainer` provides a real
#: no-network boundary: the parser runs in an AppContainer with **zero**
#: network capabilities, so it holds no ``internetClient`` capability and
#: cannot open a new outbound connection. The Job Object backend enforces
#: the *memory* cap, not network isolation, and Job Object network-rate
#: control is throttling, never isolation. Proxy-environment stripping is
#: defense in depth, never isolation.
#:
#: Explicit override for the network-isolation capability.
#:
#: On Linux this is ``True``: the namespace boundary always exists. On
#: Windows it stays ``False``, because the AppContainer boundary is
#: opt-in and is evaluated at **call time** by
#: :func:`_network_isolation_available`. This constant must not freeze
#: that decision at import time, or the opt-in could not be switched on or
#: off within one process.
#:
#: A caller that has already established the platform's capability (a
#: test double, a deployment probe) may set it to ``True`` to override the
#: gate explicitly.
NETWORK_ISOLATION_SUPPORTED: bool = HOST_PLATFORM != "win32"

#: The capability that enforces the network isolation, named for the error
#: details. This is the import-time view;
#: :func:`network_isolation_mechanism` is the call-time answer.
#:
#: On Linux the namespace launcher always exists, so the import-time value
#: names it. On Windows the AppContainer boundary is opt-in, so the
#: import-time value is the conservative "no proven boundary" -- the
#: call-time function reports the AppContainer mechanism once the opt-in
#: flag is set.
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
    explicitly unsupported while the opt-in is off: the Job Object
    backend enforces the *memory*
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
    * **Windows** -- the AppContainer backend in
      :mod:`chess_coach.pdf_ocr.windows_appcontainer` launches the parser
      in an AppContainer with **zero** network capabilities, so the token
      holds no ``internetClient`` capability and cannot open a new
      outbound connection. The Job Object backend enforces the memory cap
      only; Job Object network-rate control is throttling rather than
      isolation, and proxy-environment stripping is defense in depth, never
      isolation.

      The Windows boundary is **opt-in** through
      ``CHESS_COACH_WINDOWS_APPCONTAINER=1``. While it is off, Windows PDF
      parsing keeps raising the 501 ``internal.not_implemented`` refusal,
      exactly as before.

    Raises:
        NetworkIsolationUnsupportedError: if no network-isolation boundary
            is available. Raised BEFORE any parser process or Job target
            is created.
    """
    if _network_isolation_available():
        return
    raise NetworkIsolationUnsupportedError(
        "PDF parsing is not supported on this platform: the A-F11 "
        "no-network requirement cannot be enforced here, so no parser "
        "process is started.",
        details={
            "platform": HOST_PLATFORM,
            "required_mechanism": network_isolation_mechanism(),
            "resource": "pdf_import",
        },
    )


def _network_isolation_available() -> bool:
    """Whether a real no-network boundary is available on this host.

    Evaluated at **call time**, not import time: the Windows opt-in is a
    per-process environment flag, so the answer can change between calls
    within one process (a test sets it, a deployment sets it).

    The module-level :data:`NETWORK_ISOLATION_SUPPORTED` constant is
    honoured as an explicit override. It exists so a caller that has
    already decided the platform's capability (a test double, a
    deployment probe) can state it directly, and so the historical
    contract that the constant reflects the supported-platform state
    keeps working.
    """
    if HOST_PLATFORM != "win32":
        return True
    if NETWORK_ISOLATION_SUPPORTED:
        return True
    return windows_appcontainer_is_enabled()


def network_isolation_mechanism() -> str:
    """The name of the mechanism that enforces the no-network boundary."""
    if HOST_PLATFORM != "win32":
        return (
            "Linux user+network namespace "
            "(CLONE_NEWUSER|CLONE_NEWNET|CLONE_NEWNS)"
        )
    if windows_appcontainer_is_enabled():
        return (
            "Windows AppContainer with zero network capabilities "
            "(PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES, product-owned "
            "package SID, explicit inherited-handle allowlist)"
        )
    return "none (no proven Windows network-isolation boundary)"


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
    input_path: Path | None = None,
) -> list[str]:
    """Build the pdftoppm command-line args.

    pdftoppm is the Poppler PDF-to-image converter. The
    invocation pattern is:

        pdftoppm -r <dpi> -png -f <first> -l <last> <input> <output_prefix>

    The output files are written to `<output_prefix>-1.png`,
    `<output_prefix>-2.png`, etc. (one file per page).

    ``input_path`` names a PDF file to read. When it is ``None`` the
    parser reads the PDF from **stdin**, which is the Linux path.

    **BBF-FU-20-windows-appcontainer-network-isolation.** The Windows
    AppContainer path passes the PDF by **file path**, not stdin. An
    AppContainer token cannot traverse the user profile, and the parser's
    stdin cannot be an inherited handle under the production launch shape
    (``bInheritHandles=TRUE`` with an allowlist that contains only stdout
    and stderr). The input PDF is therefore staged next to the artifact
    directory and named on the command line.
    """
    return [
        "pdftoppm",
        "-r", str(dpi),
        "-png",
        "-f", str(first_page),
        "-l", str(last_page),
        str(input_path) if input_path is not None else "-",  # "-" reads stdin
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

        # BBF-FU-20-windows-appcontainer-network-isolation: on Windows the
        # parser runs inside an AppContainer, so the PDF is passed by FILE
        # PATH rather than stdin. The input is staged in the artifact
        # directory, which the product SID is granted access to.
        # One gate, not two independently maintained ones:
        # _network_isolation_available() is the single authority on whether
        # a no-network boundary exists on this host.
        windows_appcontainer = _network_isolation_available() and WINDOWS_JOB_SUPPORTED
        input_path: Path | None = None
        if windows_appcontainer:
            input_path = tmpdir / "input.pdf"
            input_path.write_bytes(pdf_bytes)
        args = _build_pdftoppm_args(
            dpi, first_page, last_page_arg, output_prefix, input_path=input_path,
        )

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
        #
        # BBF-FU-20-windows-appcontainer-network-isolation: on Windows the
        # launch goes through the AppContainer backend, which adds a
        # zero-capability AppContainer token and an explicit
        # inherited-handle allowlist on top of the Job containment.
        if windows_appcontainer:
            return _run_pdftoppm_in_windows_appcontainer(
                args,
                tmpdir=tmpdir,
                input_path=input_path,
                timeout_seconds=timeout_seconds,
                mem_cap_bytes=mem_cap_bytes,
            )

        if WINDOWS_JOB_SUPPORTED:
            # On Windows the Job backend is NOT a network-isolation
            # boundary -- it enforces the MEMORY cap only.  Reaching this
            # branch means the AppContainer path was not selected, so the
            # network-isolation gate above already refused.  The Job
            # backend is therefore reachable only on Linux, where the
            # namespace launcher owns the isolation.  If the platform is
            # Windows and the Job backend is the only thing left, REFUSE:
            # running the parser under a Job Object alone would execute it
            # without the no-network boundary.
            if HOST_PLATFORM == "win32":
                raise NetworkIsolationUnsupportedError(
                    "PDF parsing is not supported on this platform: the "
                    "A-F11 no-network requirement cannot be enforced here, "
                    "so no parser process is started.",
                    details={
                        "platform": HOST_PLATFORM,
                        "required_mechanism": network_isolation_mechanism(),
                        "resource": "pdf_import",
                    },
                )
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
        return _load_png_artifacts(png_files)


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
    return _load_png_artifacts(png_files)


def _load_png_artifacts(png_files: list[Path]) -> list[Image.Image]:
    """Load the PNGs an ``pdftoppm`` run produced.

    The PNGs are read as BYTES and opened from memory.  ``Image.open(p)``
    is lazy: it holds the file handle open and only reads the pixels on
    ``load()``.  The images are handed back to the caller while the
    containing temporary directory is being torn down, and WINDOWS cannot
    delete a file that is still open -- so the cleanup failed with
    ``PermissionError: [WinError 32]``.  Reading the bytes releases the
    handle immediately and the directory can be removed.

    Every image is fully loaded before it is returned, so the caller
    never depends on the file still existing.
    """
    images: list[Image.Image] = []
    for path in png_files:
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise RuntimeError(
                f"could not read the PDF parser output {path.name}: {exc}"
            ) from exc
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            images.append(image.copy())
    return images


def _run_pdftoppm_in_windows_appcontainer(
    args: list[str],
    *,
    tmpdir: Path,
    input_path: Path | None,
    timeout_seconds: int,
    mem_cap_bytes: int,
) -> list[Image.Image]:
    """Run pdftoppm inside a zero-capability AppContainer.

    **BBF-FU-20-windows-appcontainer-network-isolation.**

    The launch happens through :func:`run_in_appcontainer_job`, which
    applies, in this order and without resuming the target until every
    stage has succeeded:

    1. the product-owned AppContainer package identity, with an **empty**
       capability set (no ``internetClient``);
    2. a suspended process creation with an explicit inherited-handle
       allowlist containing only stdout and stderr;
    3. the Job Object with the per-process memory limit;
    4. Job assignment;
    5. a pre-resume verification that the token really is the product
       AppContainer with no network capability;
    6. resume.

    The error taxonomy is preserved:

    * a containment **setup** failure (package identity, capabilities,
      Job, assignment, verification, resume) raises
      :class:`NetworkIsolationSetupError`, which the route maps to 500
      ``internal.network_isolation_setup_failed``. The parser was never
      executed.
    * an **unsupported** backend raises
      :class:`NetworkIsolationUnsupportedError`, which the route maps to
      the retained 501 ``internal.not_implemented`` refusal.
    * a **parser** failure still raises ``RuntimeError``.

    There is no fallback to an unrestricted parser: a setup failure is
    never downgraded into "run it anyway".
    """
    from chess_coach.pdf_ocr.linux_sandbox import NetworkIsolationSetupError
    from chess_coach.pdf_ocr.windows_appcontainer import (
        AppContainerSetupError,
        AppContainerUnsupportedError,
        AppContainerVerificationError,
        grant_minimum_access,
        stage_parser,
    )
    from chess_coach.pdf_ocr.windows_job import (
        WindowsJobLimitExceededError,
        WindowsJobSetupError,
        WindowsJobTimeoutError,
        run_in_appcontainer_job,
    )

    # --- 1. stage the parser OUTSIDE the user profile ---------------------
    # An AppContainer token cannot traverse the user profile, so a
    # profile-resident parser is unlaunchable inside the container.
    try:
        staged = stage_parser()
    except AppContainerUnsupportedError as exc:
        # The parser cannot be staged at all -- for example it is not
        # installed.  That is the retained 501 refusal, NOT a setup
        # failure, and it must not fall through to the route's generic
        # handler (which would report 422).
        raise NetworkIsolationUnsupportedError(
            exc.message,
            details={
                "platform": HOST_PLATFORM,
                "required_mechanism": network_isolation_mechanism(),
                "resource": "pdf_import",
                "launcher": "windows_appcontainer",
                **exc.details,
            },
        ) from exc
    except AppContainerSetupError as exc:
        raise NetworkIsolationSetupError(
            "could not stage the PDF parser for the AppContainer",
            stage="parser_staging",
            details={"launcher": "windows_appcontainer", **exc.details},
        ) from exc

    # --- 2. minimum ACLs for the product SID -----------------------------
    # The product SID gets read+execute on the staged executable and its
    # runtime, and modify on the artifact directory that holds the input
    # PDF and the output PNGs. Nothing else is granted.
    try:
        # The staged parser's DIRECTORY must be granted too: the
        # restricted token needs traverse on the directory that contains
        # the DLLs to resolve them at all.  Granting only the files
        # leaves the directory without the product-SID ACE and the parser
        # dies with STATUS_DLL_NOT_FOUND.
        grant_minimum_access(
            (staged.directory, *staged.runtime_dirs), read_only=True,
        )
        grant_minimum_access((tmpdir,), read_only=False)
    except AppContainerSetupError as exc:
        raise NetworkIsolationSetupError(
            "could not apply the minimum-access ACL for the AppContainer",
            stage="acl_grant",
            details={"launcher": "windows_appcontainer", **exc.details},
        ) from exc

    # --- 3. launch inside the AppContainer --------------------------------
    stdout_path = tmpdir / "stdout.bin"
    stderr_path = tmpdir / "stderr.bin"
    argv = [str(staged.executable), *args[1:]]

    try:
        result = run_in_appcontainer_job(
            argv,
            timeout_seconds=timeout_seconds,
            limit_bytes=mem_cap_bytes,
            cwd=tmpdir,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
    except AppContainerUnsupportedError as exc:
        # The backend cannot be used here at all -- for example the parser
        # is not installed, so it cannot be staged.  That is the retained
        # 501 refusal, NOT a setup failure, and it must not fall through
        # to the route's generic handler (which would report 422).
        raise NetworkIsolationUnsupportedError(
            exc.message,
            details={
                "platform": HOST_PLATFORM,
                "required_mechanism": network_isolation_mechanism(),
                "resource": "pdf_import",
                "launcher": "windows_appcontainer",
                **exc.details,
            },
        ) from exc
    except (AppContainerVerificationError, AppContainerSetupError) as exc:
        # A containment setup failure: the parser was NEVER executed.
        raise NetworkIsolationSetupError(
            exc.message,
            stage=str(exc.details.get("stage", "appcontainer_setup")),
            details={"launcher": "windows_appcontainer", **exc.details},
        ) from exc
    except WindowsJobLimitExceededError:
        raise
    except WindowsJobTimeoutError:
        raise
    except WindowsJobSetupError:
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
    return _load_png_artifacts(png_files)


def pdftoppm_available() -> bool:
    """Check whether pdftoppm is on PATH (and thus callable).

    Used by the route layer to gracefully degrade on
    Windows hosts (where poppler is not bundled). Returns
    True if `pdftoppm` is found via `shutil.which`, False
    otherwise. The check is cheap; the route layer calls
    it once at module import time.
    """
    return shutil.which("pdftoppm") is not None
