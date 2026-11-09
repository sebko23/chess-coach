"""Windows Job Object backend — real race-free process containment.

**BBF-FU-22-B2-windows-job-object** (2026-10-28).

This module implements the Windows half of A-F11 property 4 (the 2 GB
memory cap) that `BBF-FU-22-windows-contract-correction` (B1) deliberately
left unsupported. B1 refused to launch an uncapped parser on Windows; B2
launches the parser **inside a Job Object** so the cap is real and
enforced by the kernel.

The implementation uses the standard-library :mod:`ctypes` binding to
``kernel32``. **No ``pywin32`` dependency is added**: the directive
requires an explicit suspended-create → configure → assign → resume
ordering with a retained primary-thread handle, and that ordering is
directly expressible through ``ctypes`` with exact prototypes, exact
structure sizes, and explicit handle ownership. Adding ``pywin32`` would
churn the lockfile while its high-level wrappers obscure exactly the
ordering this module has to prove.

## The race-free containment sequence

The security property B2 must establish is that **no target code may
allocate, execute, or create descendants before Job membership and the
limit are in force**. A normal launch followed by a later
``AssignProcessToJobObject`` cannot provide that: the target may already
have allocated memory or spawned children. So the order is fixed:

1. ``CreateProcessW`` with ``CREATE_SUSPENDED`` — the target exists but
   its primary thread has not run a single instruction, so it has
   allocated nothing and spawned nothing.
2. ``CreateJobObjectW`` — the Job is created.
3. ``SetInformationJobObject`` with ``JobObjectExtendedLimitInformation``
   and ``LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY`` — the per-process
   memory limit is configured **before** the target is assigned.
4. ``AssignProcessToJobObject`` — the still-suspended target joins the Job.
   Only now does the limit apply to it.
5. ``ResumeThread`` on the retained primary-thread handle — the target is
   allowed to run for the first time.

Any failure in steps 2–5 aborts the launch **without resuming the
target** (fail closed). See :func:`run_contained`.

## Limit semantics: per-process, not aggregate

The limit uses the Job Object **per-process** memory limit
(``JOB_OBJECT_LIMIT_PROCESS_MEMORY``, ``ProcessMemoryLimit``) at exactly
``2 * 1024**3`` bytes. The **aggregate** Job memory limit
(``JOB_OBJECT_LIMIT_JOB_MEMORY``, ``JobMemoryLimit``) is deliberately
**not** enabled: it is left at zero and its flag is never set.

The guarantee is therefore a **per-process ceiling inherited by
descendants** — each process in the Job gets its own 2 GiB allowance.
It is **not** a 2 GiB aggregate process-tree memory budget. A tree of
four processes may therefore use up to 4 × 2 GiB in total; what the Job
forbids is any *single* process exceeding 2 GiB.

Breakaway is never enabled (``JOB_OBJECT_LIMIT_BREAKAWAY_OK`` and
``JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK`` are not set), so descendants
inherit Job membership and cannot escape it.

## Fail-closed guarantee

No failure path can produce an unconstrained or resumed target:

* Job creation failure — the target has not been created yet.
* Limit configuration failure — the target is suspended; it is
  terminated directly with ``TerminateProcess`` (it is in no Job, so
  ``TerminateJobObject`` could not reach it).
* Process creation failure — no target exists.
* Assignment failure — the target is suspended and in no Job; it is
  terminated directly with ``TerminateProcess``. Because it never
  resumed, it cannot have created descendants.
* Resume failure — the target *is* in the Job; the Job is terminated
  with ``TerminateJobObject``.

There is no fallback to ``preexec_fn``, to source-tree execution, or to
the Linux ``RLIMIT_AS`` mechanism on Windows.

## Cleanup scope

Timeout and failure cleanup terminate **only the assigned Job** via
``TerminateJobObject``. The implementation never kills by PID list,
process name, or ancestry guesswork, so an unrelated sibling process is
never terminated. Process, thread, and Job handles are closed
deterministically in ``finally`` blocks; a cleanup failure is retained as
secondary diagnostic context and never masks the primary error.

## Limit-hit attribution

The Job is associated with an I/O completion port **before** assignment
so that job notifications are delivered for the target's whole lifetime.
The authoritative limit-violation signal is the job notification for a
per-process memory limit violation; the Job's limit-violation
information is the secondary evidence. The target's own allocation
failure is treated as *corroborating* evidence only — a nonzero parser
exit on its own is **never** classified as a limit hit.

The notification ids are those measured on the target platform (see
``docs/16_audit/BBF-FU-22-B2-windows-job-object.md``): a per-process
memory limit violation is reported as ``0x09`` and an aggregate (Job
memory) limit violation as ``0x0A``. These differ from the constants
published in some SDK headers, so the ids are pinned here from
measurement rather than from documentation, and the test suite asserts
the measured behaviour rather than a copied constant.
"""
from __future__ import annotations

import ctypes
import subprocess  # noqa: S404 -- intentional: PDF parsing requires a subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover -- import for type checking only
    from .windows_appcontainer import CapabilitySet, HandlePolicy

__all__ = [
    "WindowsJobError",
    "WindowsJobLimitExceededError",
    "WindowsJobSetupError",
    "WindowsJobTimeoutError",
    "WindowsJobCleanupError",
    "ContainedProcessResult",
    "run_in_windows_job",
    "WINDOWS_JOB_SUPPORTED",
    "JOB_OBJECT_LIMIT_BYTES",
]


# ---------------------------------------------------------------------------
# Platform gate
# ---------------------------------------------------------------------------

#: True when this module can enforce the memory cap on this host.
#:
#: The backend needs the Win32 Job Object API. It is only importable and
#: usable on Windows; on any other platform the capability is absent and
#: the caller must refuse rather than fall back.
WINDOWS_JOB_SUPPORTED: bool = sys.platform == "win32"

#: The A-F11 property-4 per-process memory ceiling, in bytes.
#:
#: This is the **per-process** limit applied through the Job Object's
#: ``ProcessMemoryLimit`` field. It is not an aggregate process-tree
#: budget.
JOB_OBJECT_LIMIT_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GiB


# The Win32 types are declared with **explicit** widths rather than via
# ``ctypes.wintypes``, for two reasons:
#
# 1. ``ctypes.wintypes`` is not importable on non-Windows platforms, and
#    this module must be importable on Linux so the shared runner can
#    branch on ``WINDOWS_JOB_SUPPORTED`` without a platform-specific
#    import guard.
# 2. ``ctypes.c_ulong`` is 4 bytes on Windows but **8 bytes** on 64-bit
#    Linux, so using it for a Win32 ``DWORD`` would silently corrupt
#    every structure on the non-Windows side. The widths are pinned here.
#
# The widths below are the Win32 definitions and are the same on every
# platform: ``DWORD`` is always 32-bit and ``HANDLE``/``LPVOID`` are
# always pointer-sized.
_LPVOID = ctypes.c_void_p
_DWORD = ctypes.c_uint32
_SIZE_T = ctypes.c_size_t
_ULONGLONG = ctypes.c_uint64
_LONGLONG = ctypes.c_int64
_BOOL = ctypes.c_int32
_WORD = ctypes.c_uint16
_HANDLE = ctypes.c_void_p
_LPWSTR = ctypes.c_wchar_p
_LPCWSTR = ctypes.c_wchar_p


# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------

#: ``CREATE_SUSPENDED`` — the primary thread is created suspended and
#: cannot run until :c:func:`ResumeThread` is called on its handle.
_CREATE_SUSPENDED = 0x00000004

#: ``CREATE_NO_WINDOW`` — the target gets no console window. It is a
#: console-application flag and is compatible with ``CREATE_SUSPENDED``.
_CREATE_NO_WINDOW = 0x08000000

#: ``JOB_OBJECT_LIMIT_PROCESS_MEMORY`` — limits the committed memory of
#: **each** process in the Job. This is the per-process limit A-F11
#: requires.
_JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100

#: ``JOB_OBJECT_LIMIT_JOB_MEMORY`` — limits the committed memory of the
#: Job **as a whole** (an aggregate tree budget).
#:
#: Deliberately **never set**. B2 must not claim an aggregate tree-wide
#: budget; this constant exists so the test suite can assert its absence.
_JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200

#: ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` — when the last handle to the
#: Job closes, the Job's processes are terminated. This is a
#: belt-and-braces backstop against an orphaned contained process.
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

#: ``JOB_OBJECT_LIMIT_BREAKAWAY_OK`` / ``..._SILENT_BREAKAWAY_OK`` —
#: would let a descendant escape the Job. Never set: descendants must
#: inherit Job membership.
_JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
_JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00004000

#: ``JOBOBJECTINFOCLASS.JobObjectExtendedLimitInformation``.
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

#: ``JOBOBJECTINFOCLASS.JobObjectAssociateCompletionPortInformation``.
_JOB_OBJECT_ASSOCIATE_COMPLETION_PORT = 7

#: ``JOBOBJECTINFOCLASS.JobObjectLimitViolationInformation``.
_JOB_OBJECT_LIMIT_VIOLATION_INFORMATION = 8

#: Size in bytes of the Job limit-violation information buffer accepted
#: by ``QueryInformationJobObject`` for
#: ``JobObjectLimitViolationInformation`` on this platform. Measured, not
#: assumed: the SDK-documented struct is smaller, but the API requires
#: the larger buffer.
_JOB_OBJECT_LIMIT_VIOLATION_BUFFER_BYTES = 96

#: Job-notification ids measured on the target platform.
#:
#: A **per-process** memory limit violation is reported as ``0x09``;
#: an **aggregate** (Job memory) violation is reported as ``0x0A``.
#: These were measured on a real Windows host with real Win32 calls and
#: they do not match the ids published in some SDK headers, so they are
#: pinned from measurement. See the module docstring of the BBF brief.
_JOB_OBJECT_MSG_PROCESS_MEMORY_LIMIT = 0x09
_JOB_OBJECT_MSG_JOB_MEMORY_LIMIT = 0x0A

#: ``WAIT_OBJECT_0`` — the wait completed.
_WAIT_OBJECT_0 = 0x00000000

#: ``WAIT_TIMEOUT`` — the wait elapsed before the object was signalled.
_WAIT_TIMEOUT = 0x00000102

#: ``INFINITE``
_INFINITE = 0xFFFFFFFF

#: ``STARTF_USESTDHANDLES``
_STARTF_USESTDHANDLES = 0x00000100

#: ``EXTENDED_STARTUPINFO_PRESENT`` — required when a process attribute
#: list is supplied.
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000

#: ``CREATE_UNICODE_ENVIRONMENT`` — required when an explicit environment
#: block is supplied.
_CREATE_UNICODE_ENVIRONMENT = 0x00000400

#: ``PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES`` — the AppContainer
#: identity of the launched target.
_PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009

#: ``PROC_THREAD_ATTRIBUTE_HANDLE_LIST`` — the explicit allowlist of
#: handles that may be inherited by the launched target.
_PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002

#: Win32 file access / sharing / creation constants for the stdio files.
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_CREATE_ALWAYS = 2
_FILE_ATTRIBUTE_NORMAL = 0x00000080
_INVALID_HANDLE_VALUE = _HANDLE(-1).value

#: Error code surfaced by ``AssignProcessToJobObject`` when the Job
#: already holds its maximum number of processes. Used by the test suite
#: to build a *real* (not mocked) assignment failure.
_ERROR_NOT_ENOUGH_QUOTA = 1816


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class WindowsJobError(Exception):
    """Base class for Windows Job Object containment failures.

    Each subclass is a distinct, observable outcome. The route layer
    maps them to distinct HTTP statuses so a containment setup failure is
    never indistinguishable from a malformed PDF, a generic parser
    failure, or a timeout.
    """

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, object] = dict(details or {})


class WindowsJobSetupError(WindowsJobError):
    """Job creation, limit configuration, assignment, or resume failed.

    Raised **before** the target is allowed to run. The target is never
    resumed on this path, so no unconstrained code ever executes.
    """


class WindowsJobLimitExceededError(WindowsJobError):
    """The target was denied or terminated by the Job's per-process limit.

    This is a distinct outcome from a generic parser failure: it is
    raised only when the Job's configured memory limit is tied to an
    attributable limit-violation signal.
    """


class WindowsJobTimeoutError(WindowsJobError):
    """The contained target exceeded its wall-clock budget.

    On this path the assigned Job is terminated and drained before the
    timeout is reported.
    """


class WindowsJobCleanupError(WindowsJobError):
    """A cleanup step failed.

    This is **secondary** diagnostic context. It is attached to the
    primary error rather than replacing it, so a cleanup problem never
    masks the parser, timeout, or containment failure that actually
    occurred.
    """


# ---------------------------------------------------------------------------
# Win32 structures
# ---------------------------------------------------------------------------

class _IO_COUNTERS(ctypes.Structure):
    """``IO_COUNTERS`` — 6 × ``ULONGLONG``."""

    _fields_ = [
        ("ReadOperationCount", _ULONGLONG),
        ("WriteOperationCount", _ULONGLONG),
        ("OtherOperationCount", _ULONGLONG),
        ("ReadTransferCount", _ULONGLONG),
        ("WriteTransferCount", _ULONGLONG),
        ("OtherTransferCount", _ULONGLONG),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    """``JOBOBJECT_BASIC_LIMIT_INFORMATION``.

    Field order and widths follow the Win32 SDK. The x64 layout puts
    ``LimitFlags`` at offset 16 with 4 bytes of padding before the
    pointer-sized fields; ``ctypes`` reproduces the SDK's alignment
    rules, so the structure size is asserted by the test suite rather
    than hard-coded here.
    """

    _fields_ = [
        ("PerProcessUserTimeLimit", _LONGLONG),
        ("PerJobUserTimeLimit", _LONGLONG),
        ("LimitFlags", _DWORD),
        ("MinimumWorkingSetSize", _SIZE_T),
        ("MaximumWorkingSetSize", _SIZE_T),
        ("ActiveProcessLimit", _DWORD),
        ("Affinity", _ULONGLONG),
        ("PriorityClass", _DWORD),
        ("SchedulingClass", _DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    """``JOBOBJECT_EXTENDED_LIMIT_INFORMATION``.

    ``ProcessMemoryLimit`` is the **per-process** limit; ``JobMemoryLimit``
    is the **aggregate** limit. B2 sets only the former.
    """

    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", _SIZE_T),
        ("JobMemoryLimit", _SIZE_T),
        ("PeakProcessMemoryUsed", _SIZE_T),
        ("PeakJobMemoryUsed", _SIZE_T),
    ]


class _JOBOBJECT_ASSOCIATE_COMPLETION_PORT(ctypes.Structure):
    """``JOBOBJECT_ASSOCIATE_COMPLETION_PORT_INFORMATION``."""

    _fields_ = [
        ("CompletionKey", _LPVOID),
        ("CompletionPort", _HANDLE),
    ]


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    """``SECURITY_ATTRIBUTES`` with ``bInheritHandle`` set.

    Handles passed to the child through ``STARTF_USESTDHANDLES`` must be
    inheritable. Ordinary Python file descriptors are **not** inherited
    by a manually created process; the stdio files are therefore opened
    with ``CreateFileW`` and this structure.
    """

    _fields_ = [
        ("nLength", _DWORD),
        ("lpSecurityDescriptor", _LPVOID),
        ("bInheritHandle", _BOOL),
    ]


class _STARTUPINFOW(ctypes.Structure):
    """``STARTUPINFOW``."""

    _fields_ = [
        ("cb", _DWORD),
        ("lpReserved", _LPWSTR),
        ("lpDesktop", _LPWSTR),
        ("lpTitle", _LPWSTR),
        ("dwX", _DWORD),
        ("dwY", _DWORD),
        ("dwXSize", _DWORD),
        ("dwYSize", _DWORD),
        ("dwXCountChars", _DWORD),
        ("dwYCountChars", _DWORD),
        ("dwFillAttribute", _DWORD),
        ("dwFlags", _DWORD),
        ("wShowWindow", _WORD),
        ("cbReserved2", _WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", _HANDLE),
        ("hStdOutput", _HANDLE),
        ("hStdError", _HANDLE),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    """``PROCESS_INFORMATION`` — carries the process and primary-thread handles."""

    _fields_ = [
        ("hProcess", _HANDLE),
        ("hThread", _HANDLE),
        ("dwProcessId", _DWORD),
        ("dwThreadId", _DWORD),
    ]


class _STARTUPINFOEX(ctypes.Structure):
    """``STARTUPINFOEXW`` — a ``STARTUPINFO`` plus a process attribute list.

    Required for the AppContainer launch: the AppContainer identity and the
    inherited-handle allowlist are both expressed as process attributes.
    """

    _fields_ = [
        ("StartupInfo", _STARTUPINFOW),
        ("lpAttributeList", _LPVOID),
    ]


class _SECURITY_CAPABILITIES(ctypes.Structure):
    """``SECURITY_CAPABILITIES`` — the AppContainer identity of a launch.

    ``Capabilities`` is a pointer to an array of capability SIDs and
    ``CapabilityCount`` its length. The production launch leaves the array
    empty (``None`` / ``0``), so the token can hold no ``internetClient``
    capability and therefore cannot open a new outbound connection.
    """

    _fields_ = [
        ("AppContainerSid", _HANDLE),
        ("Capabilities", ctypes.POINTER(_HANDLE)),
        ("CapabilityCount", _DWORD),
        ("Reserved", _DWORD),
    ]


# ---------------------------------------------------------------------------
# Win32 prototypes
# ---------------------------------------------------------------------------


#: ``ctypes.WinDLL`` and ``ctypes.get_last_error`` exist only on Windows.
#: They are reached through these module-level accessors rather than being
#: named directly, so this module stays importable **and** type-checkable on
#: Linux, where the shared runner still needs to branch on
#: :data:`WINDOWS_JOB_SUPPORTED`. Using ``getattr`` rather than a direct
#: attribute access also keeps the module free of platform-specific
#: ``type: ignore`` comments, which ``warn_unused_ignores`` would flag on
#: the platform where the attribute *does* exist.
_WINDLL_LOADER = getattr(ctypes, "WinDLL", None)
_LAST_ERROR_GETTER = getattr(ctypes, "get_last_error", None)


def _windll(name: str, **kwargs: object) -> ctypes.CDLL:
    """Load a Windows DLL (``ctypes.WinDLL``).

    Raises:
        WindowsJobSetupError: if called on a platform with no ``WinDLL``.
    """
    loader = _WINDLL_LOADER
    if loader is None:
        raise WindowsJobSetupError(
            "the Windows Job Object backend is only available on Windows",
            details={"platform": sys.platform, "stage": "platform_gate"},
        )
    library: ctypes.CDLL = loader(name, **kwargs)
    return library


def _last_error() -> int:
    """Return the last Win32 error code (``ctypes.get_last_error``)."""
    getter = _LAST_ERROR_GETTER
    if getter is None:
        return 0
    code: int = getter()
    return code


def _load_kernel32() -> ctypes.CDLL:
    """Load ``kernel32`` and install exact prototypes for every call used.

    ``ctypes.WinDLL`` and ``ctypes.get_last_error`` exist only on
    Windows. They are reached through the module-level accessors
    :func:`_windll` and :func:`_last_error` so that this module stays
    importable (and type-checkable) on Linux, where the shared runner
    still needs to branch on :data:`WINDOWS_JOB_SUPPORTED`.
    """
    k32 = _windll("kernel32", use_last_error=True)

    k32.CreateProcessW.restype = _BOOL
    k32.CreateProcessW.argtypes = [
        _LPCWSTR,          # lpApplicationName
        _LPWSTR,           # lpCommandLine
        _LPVOID,             # lpProcessAttributes
        _LPVOID,             # lpThreadAttributes
        _BOOL,             # bInheritHandles
        _DWORD,              # dwCreationFlags
        _LPVOID,             # lpEnvironment
        _LPCWSTR,          # lpCurrentDirectory
        ctypes.POINTER(_STARTUPINFOW),
        ctypes.POINTER(_PROCESS_INFORMATION),
    ]

    k32.CreateJobObjectW.restype = _HANDLE
    k32.CreateJobObjectW.argtypes = [_LPVOID, _LPCWSTR]

    k32.SetInformationJobObject.restype = _BOOL
    k32.SetInformationJobObject.argtypes = [_HANDLE, ctypes.c_int, _LPVOID, _DWORD]

    k32.AssignProcessToJobObject.restype = _BOOL
    k32.AssignProcessToJobObject.argtypes = [_HANDLE, _HANDLE]

    k32.ResumeThread.restype = _DWORD
    k32.ResumeThread.argtypes = [_HANDLE]

    k32.TerminateJobObject.restype = _BOOL
    k32.TerminateJobObject.argtypes = [_HANDLE, _DWORD]

    k32.TerminateProcess.restype = _BOOL
    k32.TerminateProcess.argtypes = [_HANDLE, _DWORD]

    k32.WaitForSingleObject.restype = _DWORD
    k32.WaitForSingleObject.argtypes = [_HANDLE, _DWORD]

    k32.CloseHandle.restype = _BOOL
    k32.CloseHandle.argtypes = [_HANDLE]

    k32.GetExitCodeProcess.restype = _BOOL
    k32.GetExitCodeProcess.argtypes = [_HANDLE, ctypes.POINTER(_DWORD)]

    k32.QueryInformationJobObject.restype = _BOOL
    k32.QueryInformationJobObject.argtypes = [
        _HANDLE, ctypes.c_int, _LPVOID, _DWORD, ctypes.POINTER(_DWORD),
    ]

    k32.CreateIoCompletionPort.restype = _HANDLE
    k32.CreateIoCompletionPort.argtypes = [_HANDLE, _HANDLE, _LPVOID, _DWORD]

    k32.GetQueuedCompletionStatus.restype = _BOOL
    k32.GetQueuedCompletionStatus.argtypes = [
        _HANDLE, ctypes.POINTER(_DWORD), ctypes.POINTER(_ULONGLONG), _LPVOID, _DWORD,
    ]

    k32.CreateFileW.restype = _HANDLE
    k32.CreateFileW.argtypes = [
        _LPCWSTR, _DWORD, _DWORD, _LPVOID, _DWORD, _DWORD, _HANDLE,
    ]

    k32.GetProcessHandleCount.restype = _BOOL
    k32.GetProcessHandleCount.argtypes = [_HANDLE, ctypes.POINTER(_DWORD)]

    k32.GetCurrentProcess.restype = _HANDLE
    k32.GetCurrentProcess.argtypes = []

    return k32


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ContainedProcessResult:
    """The outcome of a contained process run."""

    returncode: int
    stdout: bytes
    stderr: bytes
    #: True when the Job reported an attributable per-process memory
    #: limit violation for this run.
    memory_limit_violated: bool = False
    #: The job-notification ids observed during the run.
    job_notifications: tuple[int, ...] = ()
    #: Secondary cleanup diagnostics, if any. These never replace the
    #: primary outcome.
    cleanup_errors: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class _Handles:
    """Explicit ownership record for every Win32 handle this module opens.

    Every handle is closed exactly once in a ``finally`` block. A close
    that fails is recorded as a secondary diagnostic rather than raised,
    so a cleanup problem cannot mask the primary error.
    """

    job: int | None = None
    port: int | None = None
    process: int | None = None
    thread: int | None = None
    stdin_file: int | None = None
    stdout_file: int | None = None
    stderr_file: int | None = None

    def close_all(self, k32: ctypes.CDLL) -> list[str]:
        """Close every still-open handle; return non-fatal close errors."""
        errors: list[str] = []
        for name in (
            "thread",
            "process",
            "stdin_file",
            "stdout_file",
            "stderr_file",
            "port",
            "job",
        ):
            handle = getattr(self, name)
            if handle is None:
                continue
            setattr(self, name, None)
            if not k32.CloseHandle(handle):
                errors.append(f"CloseHandle({name}) failed: win32={_last_error()}")
        return errors


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _handle_to_int(handle: object) -> int:
    """Normalise a Win32 ``HANDLE`` to an ``int``.

    ``ctypes`` surfaces a ``HANDLE`` field either as an ``int`` (when the
    restype is ``c_void_p`` and the value fits) or as ``None``. This
    helper normalises both to a plain int so the handle-ownership record
    can hold every handle uniformly.
    """
    if handle is None:
        return 0
    if isinstance(handle, int):
        return handle
    value = getattr(handle, "value", None)
    if isinstance(value, int):
        return value
    # A c_void_p field read back as an int-like object. The explicit
    # annotation keeps the result typed as ``int`` (the ``int()`` call on an
    # ``object`` is unavoidably ``Any`` to mypy).
    converted: int
    try:
        converted = int(handle)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 0
    return converted


def _open_inheritable(
    k32: ctypes.CDLL,
    path: Path,
    *,
    access: int,
    creation: int,
    security: _SECURITY_ATTRIBUTES,
) -> int:
    """Open ``path`` with an inheritable Win32 handle.

    Ordinary Python descriptors are not inherited by a manually created
    process, so the stdio files are opened through ``CreateFileW`` with
    ``SECURITY_ATTRIBUTES.bInheritHandle = TRUE``.
    """
    handle = k32.CreateFileW(
        str(path),
        access,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        ctypes.byref(security),
        creation,
        _FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if not handle or handle == _INVALID_HANDLE_VALUE:
        raise WindowsJobSetupError(
            f"could not open stdio file {path}",
            details={
                "path": str(path),
                "win32_error": _last_error(),
                "stage": "stdio_open",
            },
        )
    # ``CreateFileW`` returns a ``HANDLE`` (a pointer). Normalise it to
    # an int so the ownership record can hold it unambiguously, and
    # convert back when passing it to the API.
    return int(handle) if not isinstance(handle, int) else handle


def _configure_job(
    k32: ctypes.CDLL,
    job: int,
    *,
    limit_bytes: int,
) -> None:
    """Configure the Job's **per-process** memory limit.

    Sets ``JOB_OBJECT_LIMIT_PROCESS_MEMORY`` with
    ``ProcessMemoryLimit = limit_bytes``. The aggregate
    ``JOB_OBJECT_LIMIT_JOB_MEMORY`` flag is deliberately left unset and
    ``JobMemoryLimit`` is left at zero.
    """
    info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = (
        _JOB_OBJECT_LIMIT_PROCESS_MEMORY | _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )
    info.ProcessMemoryLimit = limit_bytes
    info.JobMemoryLimit = 0

    if not k32.SetInformationJobObject(
        job,
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        raise WindowsJobSetupError(
            "could not configure the Job Object memory limit",
            details={
                "win32_error": _last_error(),
                "stage": "limit_configuration",
                "limit_bytes": limit_bytes,
                "limit_field": "ProcessMemoryLimit",
                "limit_flag": "JOB_OBJECT_LIMIT_PROCESS_MEMORY",
            },
        )


def _associate_completion_port(k32: ctypes.CDLL, job: int, port: int) -> None:
    """Associate the Job with an I/O completion port.

    Done **before** assignment so job notifications are delivered for the
    target's whole lifetime, including any limit violation.
    """
    assoc = _JOBOBJECT_ASSOCIATE_COMPLETION_PORT()
    assoc.CompletionKey = None
    assoc.CompletionPort = _HANDLE(port)
    if not k32.SetInformationJobObject(
        job,
        _JOB_OBJECT_ASSOCIATE_COMPLETION_PORT,
        ctypes.byref(assoc),
        ctypes.sizeof(assoc),
    ):
        raise WindowsJobSetupError(
            "could not associate the I/O completion port with the Job Object",
            details={
                "win32_error": _last_error(),
                "stage": "completion_port_association",
            },
        )


def _drain_job_notifications(
    k32: ctypes.CDLL,
    port: int,
    *,
    timeout_ms: int,
) -> list[int]:
    """Collect job notification ids until the port stops delivering.

    Used after the target has exited to retrieve the notifications that
    were queued while it ran (notably a memory-limit violation).
    """
    notifications: list[int] = []
    deadline_ms = timeout_ms
    while deadline_ms > 0:
        code = _DWORD()
        key = _ULONGLONG()
        overlapped = _LPVOID()
        ok = k32.GetQueuedCompletionStatus(
            port,
            ctypes.byref(code),
            ctypes.byref(key),
            ctypes.byref(overlapped),
            100,
        )
        if ok:
            notifications.append(int(code.value))
            continue
        # No packet available within the 100 ms slice: keep draining
        # until the caller's budget is exhausted.
        deadline_ms -= 100
    return notifications


def _query_limit_violation(k32: ctypes.CDLL, job: int) -> dict[str, object]:
    """Read the Job's limit-violation information (secondary evidence)."""
    buffer = ctypes.create_string_buffer(_JOB_OBJECT_LIMIT_VIOLATION_BUFFER_BYTES)
    ctypes.memset(buffer, 0, _JOB_OBJECT_LIMIT_VIOLATION_BUFFER_BYTES)
    returned = _DWORD()
    ok = k32.QueryInformationJobObject(
        job,
        _JOB_OBJECT_LIMIT_VIOLATION_INFORMATION,
        buffer,
        _JOB_OBJECT_LIMIT_VIOLATION_BUFFER_BYTES,
        ctypes.byref(returned),
    )
    if not ok:
        return {"available": False, "win32_error": _last_error()}
    raw = bytes(buffer.raw)
    return {"available": True, "raw": raw.hex()}


def _terminate_job(k32: ctypes.CDLL, job: int, exit_code: int = 1) -> None:
    """Terminate every process in the Job.

    This is the **only** scoped cleanup mechanism: it reaches exactly the
    processes assigned to this Job and nothing else. No PID list, process
    name, or ancestry heuristic is used.
    """
    k32.TerminateJobObject(job, exit_code)


def _terminate_process(k32: ctypes.CDLL, process: int, exit_code: int = 1) -> None:
    """Terminate a single still-suspended, unassigned process.

    Used only on the fail-closed assignment-failure path, where the
    target is in no Job and therefore unreachable by
    ``TerminateJobObject``. Because the target never resumed, it cannot
    have created descendants.
    """
    k32.TerminateProcess(process, exit_code)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_in_windows_job(
    argv: Sequence[str],
    *,
    stdin_bytes: bytes | None = None,
    timeout_seconds: float,
    limit_bytes: int = JOB_OBJECT_LIMIT_BYTES,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> ContainedProcessResult:
    """Run ``argv`` inside a Job Object with a per-process memory limit.

    The launch is race-free: the target is created suspended, the Job is
    created and configured, the target is assigned to the Job, and only
    then is the primary thread resumed. No target code runs before Job
    membership and the limit are established.

    Args:
        argv: the target command line.
        stdin_bytes: bytes fed to the target's stdin. ``None`` means an
            empty stdin.
        timeout_seconds: wall-clock budget for the target.
        limit_bytes: the Job's **per-process** memory limit. The default
            is the A-F11 contract value of 2 GiB.
        cwd: working directory for the target.
        env: environment for the target. ``None`` inherits the parent's.

    Returns:
        A :class:`ContainedProcessResult` describing the target's exit
        status, captured output, and any attributable memory-limit
        violation.

    Raises:
        WindowsJobSetupError: Job creation, limit configuration, process
            creation, assignment, or resume failed. The target is never
            resumed on this path.
        WindowsJobTimeoutError: the target exceeded ``timeout_seconds``.
            The assigned Job is terminated and drained first.
        WindowsJobLimitExceededError: the target was denied or terminated
            by the Job's per-process memory limit, proven by an
            attributable limit-violation signal.
    """
    if not WINDOWS_JOB_SUPPORTED:
        raise WindowsJobSetupError(
            "the Windows Job Object backend is only available on Windows",
            details={"platform": sys.platform, "stage": "platform_gate"},
        )

    k32 = _load_kernel32()
    handles = _Handles()
    cleanup_errors: list[str] = []
    job: int | None = None
    port: int | None = None
    assigned = False
    resumed = False

    workdir = Path(tempfile.mkdtemp(prefix="chess_coach_job_"))
    stdin_path = workdir / "stdin.bin"
    stdout_path = workdir / "stdout.bin"
    stderr_path = workdir / "stderr.bin"
    stdin_path.write_bytes(stdin_bytes or b"")

    security = _SECURITY_ATTRIBUTES()
    security.nLength = ctypes.sizeof(_SECURITY_ATTRIBUTES)
    security.bInheritHandle = True

    try:
        # --- 1. stdio files (inheritable handles) ------------------------
        try:
            handles.stdin_file = _open_inheritable(
                k32, stdin_path, access=_GENERIC_READ,
                creation=_OPEN_EXISTING, security=security,
            )
            handles.stdout_file = _open_inheritable(
                k32, stdout_path, access=_GENERIC_WRITE,
                creation=_CREATE_ALWAYS, security=security,
            )
            handles.stderr_file = _open_inheritable(
                k32, stderr_path, access=_GENERIC_WRITE,
                creation=_CREATE_ALWAYS, security=security,
            )
        except WindowsJobSetupError:
            raise

        # --- 2. Job creation ---------------------------------------------
        raw_job = k32.CreateJobObjectW(None, None)
        job = int(raw_job) if raw_job else 0
        if not job:
            raise WindowsJobSetupError(
                "could not create the Job Object",
                details={
                    "win32_error": _last_error(),
                    "stage": "job_creation",
                },
            )
        handles.job = job

        # --- 3. limit configuration (BEFORE assignment) ------------------
        _configure_job(k32, job, limit_bytes=limit_bytes)

        # --- 4. completion port association (BEFORE assignment) ---------
        raw_port = k32.CreateIoCompletionPort(_INVALID_HANDLE_VALUE, None, None, 1)
        port = int(raw_port) if raw_port else 0
        if not port:
            raise WindowsJobSetupError(
                "could not create the I/O completion port",
                details={
                    "win32_error": _last_error(),
                    "stage": "completion_port_creation",
                },
            )
        handles.port = port
        _associate_completion_port(k32, job, port)

        # --- 5. create the target SUSPENDED ------------------------------
        startup = _STARTUPINFOW()
        startup.cb = ctypes.sizeof(_STARTUPINFOW)
        startup.dwFlags = _STARTF_USESTDHANDLES
        startup.hStdInput = _HANDLE(handles.stdin_file)
        startup.hStdOutput = _HANDLE(handles.stdout_file)
        startup.hStdError = _HANDLE(handles.stderr_file)

        command_line = subprocess.list2cmdline(list(argv))
        process_info = _PROCESS_INFORMATION()

        env_block = None
        env_block_buf = None
        if env is not None:
            env_block_buf = _build_environment_block(env)
            env_block = ctypes.cast(env_block_buf, _LPVOID)

        created = k32.CreateProcessW(
            None,
            command_line,
            None,
            None,
            True,  # bInheritHandles — the stdio handles must be inherited
            _CREATE_SUSPENDED | _CREATE_NO_WINDOW,
            env_block,
            str(cwd) if cwd is not None else None,
            ctypes.byref(startup),
            ctypes.byref(process_info),
        )
        # The environment block must outlive the CreateProcessW call;
        # keep the buffer referenced until here, then release it.
        del env_block_buf
        if not created:
            raise WindowsJobSetupError(
                "could not create the target process",
                details={
                    "win32_error": _last_error(),
                    "stage": "process_creation",
                    "argv": list(argv),
                },
            )
        handles.process = _handle_to_int(process_info.hProcess)
        handles.thread = _handle_to_int(process_info.hThread)

        # --- 6. assign the STILL-SUSPENDED target to the Job -------------
        if not k32.AssignProcessToJobObject(job, handles.process):
            assign_error = _last_error()
            # FAIL CLOSED: the target is suspended and in no Job, so
            # TerminateJobObject cannot reach it. Terminate it directly.
            # Because it never resumed it cannot have created descendants.
            _terminate_process(k32, handles.process)
            k32.WaitForSingleObject(handles.process, 5000)
            raise WindowsJobSetupError(
                "could not assign the target process to the Job Object",
                details={
                    "win32_error": assign_error,
                    "stage": "job_assignment",
                    "process_id": int(process_info.dwProcessId),
                    "target_resumed": False,
                },
            )
        assigned = True

        # --- 7. resume ONLY now ------------------------------------------
        previous_count = k32.ResumeThread(handles.thread)
        if previous_count == 0xFFFFFFFF:
            resume_error = _last_error()
            # The target IS in the Job: terminate the Job so no contained
            # process survives a failed resume.
            _terminate_job(k32, job)
            k32.WaitForSingleObject(handles.process, 5000)
            raise WindowsJobSetupError(
                "could not resume the target's primary thread",
                details={
                    "win32_error": resume_error,
                    "stage": "resume",
                    "process_id": int(process_info.dwProcessId),
                },
            )
        resumed = True

        # --- 8. wait for completion (bounded) -----------------------------
        timeout_ms = max(1, int(timeout_seconds * 1000))
        wait_result = k32.WaitForSingleObject(handles.process, timeout_ms)

        if wait_result == _WAIT_TIMEOUT:
            # Scoped cleanup: terminate ONLY the assigned Job, then drain
            # it so the contained processes are really gone before the
            # timeout is reported.
            _terminate_job(k32, job)
            k32.WaitForSingleObject(handles.process, 10000)
            notifications = _drain_job_notifications(k32, port, timeout_ms=500)
            violation = _query_limit_violation(k32, job)
            _raise_timeout(
                argv=argv,
                timeout_seconds=timeout_seconds,
                notifications=notifications,
                violation=violation,
                limit_bytes=limit_bytes,
            )

        # --- 9. collect the outcome ---------------------------------------
        exit_code = _DWORD()
        k32.GetExitCodeProcess(handles.process, ctypes.byref(exit_code))

        # Drain the notifications queued while the target ran. A limit
        # violation is reported here, so it must be collected before the
        # Job handle is closed.
        notifications = _drain_job_notifications(k32, port, timeout_ms=1000)
        violation = _query_limit_violation(k32, job)

        stdout_bytes = stdout_path.read_bytes() if stdout_path.exists() else b""
        stderr_bytes = stderr_path.read_bytes() if stderr_path.exists() else b""

        limit_violated = _JOB_OBJECT_MSG_PROCESS_MEMORY_LIMIT in notifications

        if limit_violated:
            raise WindowsJobLimitExceededError(
                "the target exceeded the Job Object per-process memory limit",
                details={
                    "limit_bytes": limit_bytes,
                    "limit_field": "ProcessMemoryLimit",
                    "limit_flag": "JOB_OBJECT_LIMIT_PROCESS_MEMORY",
                    "aggregate_limit_enabled": False,
                    "job_notifications": list(notifications),
                    "violation_information": violation,
                    "exit_code": int(exit_code.value),
                    "argv": list(argv),
                },
            )

        return ContainedProcessResult(
            returncode=int(exit_code.value),
            stdout=stdout_bytes,
            stderr=stderr_bytes,
            memory_limit_violated=False,
            job_notifications=tuple(notifications),
        )

    finally:
        # --- deterministic handle ownership --------------------------------
        if assigned and job is not None and not resumed:
            # The target was assigned but never resumed: terminate the Job
            # so nothing survives a partially-completed launch.
            try:
                _terminate_job(k32, job)
            except OSError as exc:  # pragma: no cover - defensive
                cleanup_errors.append(f"terminate_job_on_abandon: {exc}")
        cleanup_errors.extend(handles.close_all(k32))
        try:
            _remove_workdir(workdir)
        except OSError as exc:  # pragma: no cover - defensive
            cleanup_errors.append(f"remove_workdir: {exc}")
        if cleanup_errors:
            # Cleanup problems are secondary: they are attached to the
            # primary outcome rather than replacing it.
            _attach_cleanup_errors(cleanup_errors)


def run_in_appcontainer_job(
    argv: Sequence[str],
    *,
    timeout_seconds: float,
    limit_bytes: int = JOB_OBJECT_LIMIT_BYTES,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    stdin_path: Path | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    package_sid: str | None = None,
    expected_package_sid: str | None = None,
    handle_policy: HandlePolicy | None = None,
) -> ContainedProcessResult:
    """Run ``argv`` inside an AppContainer **and** a Job Object.

    **BBF-FU-20-windows-appcontainer-network-isolation.**

    This is the Windows counterpart of the Linux combined sandbox launcher.
    It adds two containment layers on top of the Job Object backend that
    :func:`run_in_windows_job` already provides:

    * **AppContainer with zero network capabilities.** The target's token
      carries the product-owned AppContainer SID and an empty capability
      set, so it holds no ``internetClient`` capability and therefore
      cannot open a new outbound network connection. Measured on a native
      Windows host: the restricted child timed out on an outbound TCP
      connect while an unrestricted control in the same run connected.

    * **An explicit inherited-handle allowlist.** The target is created
      with ``bInheritHandles=TRUE`` and a
      ``PROC_THREAD_ATTRIBUTE_HANDLE_LIST`` containing exactly the
      parser's stdout and stderr handles. This is what stops an
      already-connected socket from crossing into the parser: an
      AppContainer token does **not** revoke an inherited network handle,
      so the handle policy — not the container — is the mitigation.
      Measured: with the populated allowlist the child reported the
      socket as ``PRESENT ... inheritable=False`` and every send on it
      failed with ``WSAENOTSOCK`` (10038), while the same socket was
      usable in the positive control that used no allowlist.

      The **empty** allowlist is never used: it was measured not to
      provide an empty allowlist, because the child's own standard
      handles occupy the same handle values.

    The ordering is fixed and fails closed at every stage:

    1. prepare the package identity and the zero-capability set;
    2. create the target **suspended** with the attribute list;
    3. create and configure the Job with the per-process memory limit;
    4. assign the still-suspended target to the Job;
    5. verify the target's AppContainer identity and capabilities **while
       it is still suspended**;
    6. resume only after every stage above has succeeded.

    Any failure in steps 1-5 aborts the launch **without resuming the
    target**, so no unconstrained parser code ever runs.

    There is no fallback to an unrestricted parser, no firewall rule, no
    proxy stripping, and no Job rate control used as a substitute for
    isolation.

    Args:
        argv: the parser command line.
        timeout_seconds: wall-clock budget for the target.
        limit_bytes: the Job's **per-process** memory limit.
        cwd: the target's working directory.
        env: the environment for the target.
        stdin_path: a file to attach as the target's stdin.
        stdout_path: a file to receive the target's stdout.
        stderr_path: a file to receive the target's stderr.
        package_sid: the AppContainer SID to launch under. Defaults to
            the product-owned SID.

    Returns:
        A :class:`ContainedProcessResult`.

    Raises:
        AppContainerUnsupportedError: the AppContainer backend cannot be
            used on this host.
        AppContainerSetupError: a containment stage failed; the parser was
            never executed.
        AppContainerVerificationError: the launched token did not match
            the expected AppContainer identity; the parser was never
            resumed.
        WindowsJobLimitExceededError: the target was denied or terminated
            by the Job's per-process memory limit.
        WindowsJobTimeoutError: the target exceeded its budget.
        WindowsJobSetupError: the Job lifecycle failed.
    """
    from .windows_appcontainer import (
        PRODUCT_PACKAGE_SID,
        AppContainerSetupError,
        assert_verified,
        build_launch_plan,
        parse_sid_string,
        register_profile,
        verify_token,
    )

    expected_sid = package_sid or PRODUCT_PACKAGE_SID
    plan = build_launch_plan()
    capabilities = plan.capabilities
    policy = handle_policy if handle_policy is not None else plan.handle_policy

    k32 = _load_kernel32()
    k32.CreateProcessW.restype = _BOOL
    k32.CreateProcessW.argtypes = [
        _LPWSTR, _LPWSTR, _LPVOID, _LPVOID, _BOOL, _DWORD,
        _LPVOID, _LPWSTR, _LPVOID, _LPVOID,
    ]
    k32.InitializeProcThreadAttributeList.restype = _BOOL
    k32.InitializeProcThreadAttributeList.argtypes = [
        _LPVOID, _DWORD, _DWORD, ctypes.POINTER(ctypes.c_size_t),
    ]
    k32.UpdateProcThreadAttribute.restype = _BOOL
    k32.UpdateProcThreadAttribute.argtypes = [
        _LPVOID, _DWORD, _LPVOID, _LPVOID, ctypes.c_size_t, _LPVOID, _LPVOID,
    ]
    k32.DeleteProcThreadAttributeList.restype = None
    k32.DeleteProcThreadAttributeList.argtypes = [_LPVOID]

    handles = _Handles()
    cleanup_errors: list[str] = []
    job: int | None = None
    port: int | None = None
    assigned = False
    resumed = False
    attribute_list = None
    keepalive: list[object] = []

    # Windows requires an AppContainer SID to be known to the system before
    # it can back a launched token: an unregistered SID fails at process
    # creation with ERROR_FILE_NOT_FOUND. Registration is per-user and
    # needs no administrator rights.
    from .windows_appcontainer import profile_is_registered

    if not profile_is_registered(expected_sid):
        register_profile(sid_string=expected_sid)

    # The SID allocation is only needed to populate the
    # SECURITY_CAPABILITIES attribute, so it is released once
    # CreateProcessW has returned.  It is tracked so the finally block
    # frees it on every path, including the failure paths.
    from .windows_appcontainer import free_sid

    package_sid_pointer = parse_sid_string(expected_sid)
    sid_allocation = package_sid_pointer
    workdir = Path(tempfile.mkdtemp(prefix="chess_coach_appcontainer_"))
    try:
        # --- 1. the standard handles the parser may inherit ----------------
        security = _SECURITY_ATTRIBUTES()
        security.nLength = ctypes.sizeof(_SECURITY_ATTRIBUTES)
        security.bInheritHandle = True

        stdin_handle = 0
        stdout_handle = 0
        stderr_handle = 0
        try:
            if stdin_path is not None:
                stdin_handle = _open_inheritable(
                    k32, stdin_path, access=_GENERIC_READ,
                    creation=_OPEN_EXISTING, security=security,
                )
                handles.stdin_file = stdin_handle
            if stdout_path is not None:
                stdout_handle = _open_inheritable(
                    k32, stdout_path, access=_GENERIC_WRITE,
                    creation=_CREATE_ALWAYS, security=security,
                )
                handles.stdout_file = stdout_handle
            if stderr_path is not None:
                stderr_handle = _open_inheritable(
                    k32, stderr_path, access=_GENERIC_WRITE,
                    creation=_CREATE_ALWAYS, security=security,
                )
                handles.stderr_file = stderr_handle
        except WindowsJobSetupError:
            raise

        # --- 2. the attribute list: capabilities + handle allowlist ---------
        permitted = policy.permitted_handles(
            stdout=stdout_handle or None, stderr=stderr_handle or None,
        )
        # B1 (fail-closed): the production policy REQUIRES a populated
        # allowlist.  An empty allowlist is indistinguishable, to the
        # attribute-list builder, from "no allowlist requested" -- and
        # omitting the attribute while bInheritHandles stays TRUE lets
        # EVERY inheritable parent handle cross into the child.  That is
        # exactly the bypass shape, so an empty allowlist is a setup
        # failure, never a silent downgrade.
        if policy.use_explicit_allowlist and not permitted:
            raise AppContainerSetupError(
                "the parser launch requires the stdout and stderr handles so "
                "the explicit inherited-handle allowlist can be populated; an "
                "empty allowlist would let every inheritable handle cross "
                "into the child",
                details={
                    "stage": "handle_policy",
                    "stdout_path": str(stdout_path) if stdout_path else None,
                    "stderr_path": str(stderr_path) if stderr_path else None,
                },
            )
        attribute_list, keepalive = _build_appcontainer_attribute_list(
            k32,
            capabilities=capabilities,
            package_sid_pointer=package_sid_pointer,
            handle_list=permitted,
            include_handle_list=policy.use_explicit_allowlist,
        )

        # --- 3. the Job is created and configured BEFORE assignment --------
        raw_job = k32.CreateJobObjectW(None, None)
        job = int(raw_job) if raw_job else 0
        if not job:
            raise AppContainerSetupError(
                "could not create the Job Object for the AppContainer target",
                details={
                    "win32_error": _last_error(),
                    "stage": "job_creation",
                },
            )
        _configure_job(k32, job, limit_bytes=limit_bytes)
        # The Job handle is owned by the _Handles record, so it is closed
        # deterministically in the finally block.  Without this the Job
        # handle (and the kill-on-close backstop it carries) leaked on
        # every launch.
        handles.job = job

        raw_port = k32.CreateIoCompletionPort(_INVALID_HANDLE_VALUE, None, None, 1)
        port = int(raw_port) if raw_port else 0
        if not port:
            raise AppContainerSetupError(
                "could not create the I/O completion port",
                details={
                    "win32_error": _last_error(),
                    "stage": "completion_port_creation",
                },
            )
        handles.port = port
        _associate_completion_port(k32, job, port)

        # --- 4. create the target SUSPENDED with the attribute list --------
        startup = _STARTUPINFOW()
        # With EXTENDED_STARTUPINFO_PRESENT the STARTUPINFO's cb field must
        # be the size of the STARTUPINFOEX, not of the STARTUPINFO.
        startup.cb = ctypes.sizeof(_STARTUPINFOEX)
        startup.dwFlags = _STARTF_USESTDHANDLES
        startup.hStdInput = _HANDLE(stdin_handle or None)
        startup.hStdOutput = _HANDLE(stdout_handle or None)
        startup.hStdError = _HANDLE(stderr_handle or None)

        startup_ex = _STARTUPINFOEX()
        startup_ex.StartupInfo = startup
        # _LPVOID is already c_void_p, so the attribute buffer's address
        # is assigned directly; a second ctypes.cast cannot convert to a
        # pointer type.
        startup_ex.lpAttributeList = ctypes.addressof(attribute_list)

        command_line = subprocess.list2cmdline(list(argv))
        process_info = _PROCESS_INFORMATION()

        env_block = None
        env_block_buf = None
        if env is not None:
            env_block_buf = _build_environment_block(env)
            env_block = ctypes.cast(env_block_buf, _LPVOID)

        flags = _CREATE_SUSPENDED | _EXTENDED_STARTUPINFO_PRESENT | _CREATE_NO_WINDOW
        if env is not None:
            flags |= _CREATE_UNICODE_ENVIRONMENT

        created = k32.CreateProcessW(
            None,
            command_line,
            None,
            None,
            # bInheritHandles=TRUE is REQUIRED for the explicit handle
            # allowlist to be honoured. With FALSE, CreateProcessW fails
            # with ERROR_INVALID_PARAMETER (87) -- measured.
            bool(policy.inherit_handles),
            flags,
            env_block,
            str(cwd) if cwd is not None else None,
            ctypes.byref(startup_ex),
            ctypes.byref(process_info),
        )
        del env_block_buf
        if not created:
            raise AppContainerSetupError(
                "could not create the AppContainer target process",
                details={
                    "win32_error": _last_error(),
                    "stage": "process_creation",
                    "argv": list(argv),
                    "package_sid": expected_sid,
                },
            )
        handles.process = _handle_to_int(process_info.hProcess)
        handles.thread = _handle_to_int(process_info.hThread)

        # --- 5. assign the STILL-SUSPENDED target to the Job ---------------
        if not k32.AssignProcessToJobObject(job, handles.process):
            assign_error = _last_error()
            # FAIL CLOSED: the target is suspended and in no Job, so it is
            # terminated directly. Because it never resumed it cannot have
            # created descendants or opened a socket.
            _terminate_process(k32, handles.process)
            k32.WaitForSingleObject(handles.process, 5000)
            raise AppContainerSetupError(
                "could not assign the AppContainer target to the Job Object",
                details={
                    "win32_error": assign_error,
                    "stage": "job_assignment",
                    "process_id": int(process_info.dwProcessId),
                    "target_resumed": False,
                },
            )
        assigned = True

        # --- 6. verify the token WHILE THE TARGET IS STILL SUSPENDED -------
        verification = verify_token(
            handles.process,
            expected_sid=expected_package_sid or expected_sid,
            expected_capabilities=capabilities,
        )
        if not verification.ok:
            # FAIL CLOSED: terminate the suspended target. It has not run a
            # single instruction, so it cannot have created descendants or
            # opened a socket.
            _terminate_process(k32, handles.process)
            k32.WaitForSingleObject(handles.process, 5000)
            assert_verified(verification)

        # --- 7. resume ONLY now -------------------------------------------
        previous_count = k32.ResumeThread(handles.thread)
        if previous_count == 0xFFFFFFFF:
            resume_error = _last_error()
            _terminate_job(k32, job)
            k32.WaitForSingleObject(handles.process, 5000)
            raise AppContainerSetupError(
                "could not resume the AppContainer target's primary thread",
                details={
                    "win32_error": resume_error,
                    "stage": "resume",
                    "process_id": int(process_info.dwProcessId),
                    "target_resumed": False,
                },
            )
        resumed = True

        # --- 8. wait for completion (bounded) ------------------------------
        timeout_ms = max(1, int(timeout_seconds * 1000))
        wait_result = k32.WaitForSingleObject(handles.process, timeout_ms)

        if wait_result == _WAIT_TIMEOUT:
            _terminate_job(k32, job)
            k32.WaitForSingleObject(handles.process, 10000)
            notifications = _drain_job_notifications(k32, port, timeout_ms=500)
            violation = _query_limit_violation(k32, job)
            _raise_timeout(
                argv=argv,
                timeout_seconds=timeout_seconds,
                notifications=notifications,
                violation=violation,
                limit_bytes=limit_bytes,
            )

        # --- 9. collect the outcome ----------------------------------------
        exit_code = _DWORD()
        k32.GetExitCodeProcess(handles.process, ctypes.byref(exit_code))

        notifications = _drain_job_notifications(k32, port, timeout_ms=1000)
        violation = _query_limit_violation(k32, job)

        stdout_bytes = stdout_path.read_bytes() if stdout_path and stdout_path.exists() else b""
        stderr_bytes = stderr_path.read_bytes() if stderr_path and stderr_path.exists() else b""

        if _JOB_OBJECT_MSG_PROCESS_MEMORY_LIMIT in notifications:
            raise WindowsJobLimitExceededError(
                "the target exceeded the Job Object per-process memory limit",
                details={
                    "limit_bytes": limit_bytes,
                    "limit_field": "ProcessMemoryLimit",
                    "limit_flag": "JOB_OBJECT_LIMIT_PROCESS_MEMORY",
                    "aggregate_limit_enabled": False,
                    "job_notifications": list(notifications),
                    "violation_information": violation,
                    "exit_code": int(exit_code.value),
                    "argv": list(argv),
                },
            )

        return ContainedProcessResult(
            returncode=int(exit_code.value),
            stdout=stdout_bytes,
            stderr=stderr_bytes,
            memory_limit_violated=False,
            job_notifications=tuple(notifications),
        )

    finally:
        if assigned and job is not None and not resumed:
            try:
                _terminate_job(k32, job)
            except OSError as exc:  # pragma: no cover - defensive
                cleanup_errors.append(f"terminate_job_on_abandon: {exc}")
        cleanup_errors.extend(handles.close_all(k32))
        if attribute_list is not None:
            try:
                k32.DeleteProcThreadAttributeList(attribute_list)
            except Exception as exc:  # pragma: no cover - defensive
                cleanup_errors.append(f"delete_attribute_list: {exc}")
        # The SID allocation is released on every path, including the
        # failure paths, so a launch never leaks it.
        try:
            free_sid(sid_allocation)
        except Exception as exc:  # pragma: no cover - defensive
            cleanup_errors.append(f"free_sid: {exc}")
        try:
            _remove_workdir(workdir)
        except OSError as exc:  # pragma: no cover - defensive
            cleanup_errors.append(f"remove_workdir: {exc}")
        if cleanup_errors:
            _attach_cleanup_errors(cleanup_errors)


def _build_appcontainer_attribute_list(
    k32: ctypes.CDLL,
    *,
    capabilities: CapabilitySet,
    package_sid_pointer: ctypes.c_void_p,
    handle_list: Sequence[int],
    include_handle_list: bool = True,
) -> tuple[ctypes.Array[ctypes.c_char], list[object]]:
    """Build the ``PROC_THREAD_ATTRIBUTE_LIST`` for an AppContainer launch.

    The list carries two attributes:

    * ``PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES`` — the AppContainer
      identity (the product SID) and the capability set (empty in
      production).
    * ``PROC_THREAD_ATTRIBUTE_HANDLE_LIST`` — the explicit allowlist of
      handles that may cross into the child. It is added only when
      ``include_handle_list`` is true; when it is false, **no** handle list
      is applied and every inheritable handle in the parent crosses into
      the child. That is the bypass shape, used only to keep the
      threat-model fact demonstrable.

    Returns the attribute buffer plus the objects that must stay alive
    until after ``CreateProcessW`` returns: the ``SECURITY_CAPABILITIES``
    structure and the handle array. Letting either be garbage-collected
    early corrupts the attribute list.
    """
    from .windows_appcontainer import AppContainerSetupError

    # An explicitly requested allowlist that is EMPTY is refused: applying
    # it would mean "no handle list at all", which with bInheritHandles=TRUE
    # lets every inheritable parent handle cross into the child.
    if include_handle_list and not handle_list:
        raise AppContainerSetupError(
            "the inherited-handle allowlist was requested but is empty",
            details={"stage": "attribute_list"},
        )
    use_list = bool(include_handle_list and handle_list)
    count = 2 if use_list else 1
    size = ctypes.c_size_t(0)
    k32.InitializeProcThreadAttributeList(None, count, 0, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    if not k32.InitializeProcThreadAttributeList(buf, count, 0, ctypes.byref(size)):
        raise AppContainerSetupError(
            "could not initialise the process attribute list",
            details={
                "win32_error": _last_error(),
                "stage": "attribute_list",
            },
        )
    keep: list[object] = []

    caps = _SECURITY_CAPABILITIES()
    caps.AppContainerSid = package_sid_pointer
    if capabilities.sids:
        # The production set is empty by construction (build_launch_plan
        # refuses a network-capable set).  Rather than silently dropping a
        # non-empty set, refuse it here too.
        raise AppContainerSetupError(
            "a non-empty capability set must never be used for the parser",
            details={
                "stage": "attribute_list",
                "capabilities": list(capabilities.sids),
            },
        )
    caps.CapabilityCount = 0
    caps.Capabilities = None
    keep.append(caps)

    if not k32.UpdateProcThreadAttribute(
        buf,
        0,
        _PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
        ctypes.byref(caps),
        ctypes.sizeof(caps),
        None,
        None,
    ):
        raise AppContainerSetupError(
            "could not set the AppContainer security capabilities attribute",
            details={
                "win32_error": _last_error(),
                "stage": "attribute_list",
            },
        )

    if use_list:
        handle_array = (ctypes.c_void_p * len(handle_list))(
            *[int(h) for h in handle_list]
        )
        keep.append(handle_array)
        if not k32.UpdateProcThreadAttribute(
            buf,
            0,
            _PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
            ctypes.byref(handle_array),
            ctypes.sizeof(handle_array),
            None,
            None,
        ):
            raise AppContainerSetupError(
                "could not set the inherited-handle allowlist attribute",
                details={
                    "win32_error": _last_error(),
                    "stage": "attribute_list",
                },
            )

    return buf, keep


def _build_environment_block(env: dict[str, str]) -> ctypes.Array[ctypes.c_char]:
    """Build a Windows environment block for ``CreateProcessW``.

    The block is a sequence of ``KEY=VALUE`` strings in UTF-16LE,
    terminated by an extra NUL. The returned buffer must stay alive
    until after ``CreateProcessW`` returns.
    """
    block = bytearray()
    for key in sorted(env):
        block += f"{key}={env[key]}\0".encode("utf-16-le")
    block += b"\0\0"
    raw = bytes(block)
    buf = (ctypes.c_char * len(raw))()
    ctypes.memmove(buf, raw, len(raw))
    return buf


def _remove_workdir(workdir: Path) -> None:
    """Remove the temporary work directory, ignoring a missing directory."""
    import shutil

    shutil.rmtree(workdir, ignore_errors=True)


def _attach_cleanup_errors(errors: list[str]) -> None:
    """Record cleanup diagnostics without masking the primary error.

    When an exception is propagating, the cleanup diagnostics are attached
    to it. When the call succeeded, they are logged. Neither path
    replaces the primary outcome.
    """
    import logging

    logger = logging.getLogger(__name__)
    exc = sys.exc_info()[1]
    if exc is not None and isinstance(exc, WindowsJobError):
        existing = exc.details.get("cleanup_errors")
        if isinstance(existing, list):
            existing.extend(errors)
        else:
            exc.details["cleanup_errors"] = list(errors)
        return
    logger.warning("windows job cleanup diagnostics: %s", "; ".join(errors))


def _raise_timeout(
    *,
    argv: Sequence[str],
    timeout_seconds: float,
    notifications: list[int],
    violation: dict[str, object],
    limit_bytes: int,
) -> None:
    """Raise the timeout error, or the limit error if a violation is attributable.

    A timeout that is *also* a limit violation is reported as a limit
    violation, because that is the more specific and more actionable
    outcome. The Job has already been terminated and drained by the
    caller before this function runs.
    """
    if _JOB_OBJECT_MSG_PROCESS_MEMORY_LIMIT in notifications:
        raise WindowsJobLimitExceededError(
            "the target exceeded the Job Object per-process memory limit",
            details={
                "limit_bytes": limit_bytes,
                "limit_field": "ProcessMemoryLimit",
                "limit_flag": "JOB_OBJECT_LIMIT_PROCESS_MEMORY",
                "aggregate_limit_enabled": False,
                "job_notifications": list(notifications),
                "violation_information": violation,
                "timeout_seconds": timeout_seconds,
                "argv": list(argv),
            },
        )
    raise WindowsJobTimeoutError(
        f"the contained target exceeded its {timeout_seconds}s budget",
        details={
            "timeout_seconds": timeout_seconds,
            "job_notifications": list(notifications),
            "violation_information": violation,
            "argv": list(argv),
        },
    )


def _current_process_handle_count() -> int:
    """Return the current process's open-handle count (test helper)."""
    k32 = _load_kernel32()
    count = _DWORD()
    k32.GetProcessHandleCount(k32.GetCurrentProcess(), ctypes.byref(count))
    return int(count.value)


def _get_current_process() -> int:
    """Return the pseudo-handle for the current process (test helper)."""
    k32 = _load_kernel32()
    return int(k32.GetCurrentProcess())
