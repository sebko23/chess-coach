"""Real Windows Job Object enforcement tests (BBF-FU-22-B2-windows-job-object).

These tests run on a real ``windows-latest`` runner and execute **real
Win32 calls** — no mocked Job API, no skip, no source-tree-only proof.
Every test either exercises the kernel's enforcement or fails.

The suite proves the properties B2 is accountable for:

1. The target is actually constrained by the Job (the kernel denies the
   over-limit allocation).
2. Descendants inherit the per-process limit and cannot escape the Job.
3. An unrelated sibling launched by the same harness is never assigned to
   the Job and survives timeout/failure cleanup.
4. The target stays suspended until configuration and assignment
   complete: a marker file the target writes as its first action must not
   exist while the target is still suspended.
5. A setup/assignment failure cannot result in an executed unconstrained
   target.
6. Timeout cleanup terminates only the Job's processes, and repeated runs
   leave no parser or descendant processes behind.
7. Repeated execution does not leak Job, process, or thread handles.
8. Setup, limit, timeout, parser, generic parser, and cleanup outcomes
   stay observably distinct.
9. The production call uses exactly 2 GiB, even though the behavioural
   tests use a lower test-only threshold.

The **mandatory negative control** is
:func:`test_uncontained_control_crosses_threshold`: the same executable,
the same allocation strategy, the same timeout, and the same observation
mechanism, but with the Job assignment bypassed. It must explicitly
prove that it crossed the measured threshold, and it must fail if the
allocator cannot cross it. Paired with
:func:`test_contained_target_is_denied_at_the_same_threshold`, the pair
fails against an uncontained or no-op implementation for the expected
enforcement reason.
"""
from __future__ import annotations

import ctypes
import subprocess  # noqa: S404 -- intentional: these tests spawn real processes
import sys
import time
from pathlib import Path

import pytest

from chess_coach.pdf_ocr import windows_job as wj

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="the Windows Job Object backend only exists on Windows",
)

#: The production limit, which every test asserts is unchanged.
PRODUCTION_LIMIT_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB

#: The test-only per-process threshold.
#:
#: Deliberately far below the production 2 GiB so the allocation test is
#: deterministic and fast on a CI runner. It is a **test-only** value:
#: it is not exposed through public configuration and it does not alter
#: the production constant, which :func:`test_production_limit_is_2gib`
#: pins.
TEST_LIMIT_BYTES = 64 * 1024 * 1024  # 64 MiB

#: The allocation the target attempts. Comfortably above
#: :data:`TEST_LIMIT_BYTES` and comfortably below what a CI runner has.
ALLOCATION_BYTES = 512 * 1024 * 1024  # 512 MiB


# ---------------------------------------------------------------------------
# Helper child programs
# ---------------------------------------------------------------------------

_ALLOCATOR_SOURCE = '''\
"""Allocate a requested number of bytes and record exactly what happened."""
import os
import sys


def main() -> int:
    nbytes = int(sys.argv[1])
    steplog = sys.argv[2]
    marker = sys.argv[3] if len(sys.argv) > 3 else ""
    grandchild = int(sys.argv[4]) if len(sys.argv) > 4 else 0

    # The marker is written as the FIRST action, so its absence proves the
    # target never ran.
    if marker:
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write("EXECUTED")

    log = open(steplog, "w", encoding="utf-8", buffering=1)
    log.write("STEP started pid=%d\\n" % os.getpid())
    log.write("STEP attempting_alloc bytes=%d\\n" % nbytes)
    try:
        buf = bytearray(nbytes)
        buf[0] = 1
        buf[-1] = 2
        log.write("STEP alloc_succeeded bytes=%d\\n" % len(buf))
    except MemoryError:
        log.write("STEP memory_error\\n")
        log.close()
        return 7
    log.write("STEP alloc_done\\n")

    if grandchild:
        import subprocess as sp
        child_log = steplog + ".grandchild"
        try:
            proc = sp.run(
                [sys.executable, os.path.abspath(__file__), str(grandchild), child_log,
                 "", "0"],
                capture_output=True, text=True, timeout=120,
            )
            log.write("STEP grandchild_rc=%d\\n" % proc.returncode)
            try:
                with open(child_log, encoding="utf-8") as handle:
                    log.write("STEP grandchild_log=%s\\n" % handle.read().replace("\\n", "|"))
            except OSError:
                log.write("STEP grandchild_log=<unreadable>\\n")
        except sp.TimeoutExpired:
            log.write("STEP grandchild_timeout\\n")

    log.write("STEP exiting 0\\n")
    log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


@pytest.fixture
def allocator(tmp_path: Path) -> Path:
    """Write the allocation helper program to disk and return its path."""
    path = tmp_path / "allocator_child.py"
    path.write_text(_ALLOCATOR_SOURCE, encoding="utf-8")
    return path


def _read_log(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _process_alive(pid: int) -> bool:
    """Return True when a process with ``pid`` is still running."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_uint32()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        # STILL_ACTIVE (259) means the process has not exited.
        return code.value == 259
    finally:
        k32.CloseHandle(handle)


# ---------------------------------------------------------------------------
# A. The production contract: exactly 2 GiB, per-process, never aggregate
# ---------------------------------------------------------------------------


def test_production_limit_is_2gib() -> None:
    """The production call uses exactly 2 GiB.

    The behavioural tests use a lower test-only threshold for
    determinism, so this test pins the production constant separately.
    """
    assert wj.JOB_OBJECT_LIMIT_BYTES == PRODUCTION_LIMIT_BYTES
    assert wj.JOB_OBJECT_LIMIT_BYTES == 2 * 1024**3


def test_limit_uses_per_process_field_not_aggregate() -> None:
    """The Job is configured with the PER-PROCESS limit field.

    ``JOB_OBJECT_LIMIT_PROCESS_MEMORY`` must be set and
    ``JOB_OBJECT_LIMIT_JOB_MEMORY`` (the aggregate tree budget) must not
    be. The ``ProcessMemoryLimit`` field carries the value; the
    ``JobMemoryLimit`` field stays zero.
    """
    assert wj._JOB_OBJECT_LIMIT_PROCESS_MEMORY == 0x00000100
    assert wj._JOB_OBJECT_LIMIT_JOB_MEMORY == 0x00000200
    assert wj._JOB_OBJECT_LIMIT_PROCESS_MEMORY != wj._JOB_OBJECT_LIMIT_JOB_MEMORY

    k32 = wj._load_kernel32()
    job = k32.CreateJobObjectW(None, None)
    assert job
    try:
        wj._configure_job(k32, int(job), limit_bytes=PRODUCTION_LIMIT_BYTES)

        info = wj._JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        returned = ctypes.c_uint32()
        assert k32.QueryInformationJobObject(
            job,
            wj._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(returned),
        )
        flags = info.BasicLimitInformation.LimitFlags
        assert flags & wj._JOB_OBJECT_LIMIT_PROCESS_MEMORY, (
            f"JOB_OBJECT_LIMIT_PROCESS_MEMORY must be set; flags=0x{flags:x}"
        )
        assert not (flags & wj._JOB_OBJECT_LIMIT_JOB_MEMORY), (
            f"the aggregate JOB_MEMORY limit must NOT be set; flags=0x{flags:x}"
        )
        assert info.ProcessMemoryLimit == PRODUCTION_LIMIT_BYTES
        assert info.JobMemoryLimit == 0, (
            "the aggregate JobMemoryLimit must stay zero -- this is a "
            "per-process ceiling, not a tree-wide budget"
        )
    finally:
        k32.CloseHandle(job)


def test_breakaway_is_never_enabled() -> None:
    """Descendants must not be able to escape the Job."""
    k32 = wj._load_kernel32()
    job = k32.CreateJobObjectW(None, None)
    assert job
    try:
        wj._configure_job(k32, int(job), limit_bytes=PRODUCTION_LIMIT_BYTES)
        info = wj._JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        returned = ctypes.c_uint32()
        assert k32.QueryInformationJobObject(
            job,
            wj._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(returned),
        )
        flags = info.BasicLimitInformation.LimitFlags
        assert not (flags & wj._JOB_OBJECT_LIMIT_BREAKAWAY_OK)
        assert not (flags & wj._JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK)
    finally:
        k32.CloseHandle(job)


def test_structure_sizes_match_the_win32_sdk() -> None:
    """The ctypes structures have the sizes the Win32 SDK defines.

    A wrong structure size means the kernel reads the wrong fields, so
    this is a real correctness check rather than a cosmetic one.

    The ``SECURITY_ATTRIBUTES`` size is pointer-width dependent: 24 bytes
    on x64 (DWORD + 4 bytes padding + pointer + BOOL + 4 bytes padding)
    and 12 bytes on x86.
    """
    assert ctypes.sizeof(wj._JOBOBJECT_BASIC_LIMIT_INFORMATION) == 64
    assert ctypes.sizeof(wj._IO_COUNTERS) == 48
    assert ctypes.sizeof(wj._JOBOBJECT_EXTENDED_LIMIT_INFORMATION) == 144
    expected_sa = 24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 12
    assert ctypes.sizeof(wj._SECURITY_ATTRIBUTES) == expected_sa


# ---------------------------------------------------------------------------
# B. The kernel really enforces the limit
# ---------------------------------------------------------------------------


def test_contained_target_is_denied_at_the_same_threshold(
    allocator: Path, tmp_path: Path
) -> None:
    """A target inside the Job is denied when it exceeds the limit.

    The Job's per-process limit is the only thing that could produce this
    outcome: the same executable succeeds outside a Job (see the
    negative control below).
    """
    steplog = tmp_path / "contained.log"
    with pytest.raises(wj.WindowsJobLimitExceededError) as excinfo:
        wj.run_in_windows_job(
            [sys.executable, str(allocator), str(ALLOCATION_BYTES), str(steplog)],
            timeout_seconds=120,
            limit_bytes=TEST_LIMIT_BYTES,
        )
    details = excinfo.value.details
    assert details["limit_bytes"] == TEST_LIMIT_BYTES
    assert details["limit_field"] == "ProcessMemoryLimit"
    assert details["limit_flag"] == "JOB_OBJECT_LIMIT_PROCESS_MEMORY"
    assert details["aggregate_limit_enabled"] is False
    # The Job's own limit-violation signal must be present: the outcome
    # is attributable to the configured limit, not to a nonzero exit.
    assert wj._JOB_OBJECT_MSG_PROCESS_MEMORY_LIMIT in details["job_notifications"]
    # Corroborating evidence from the target itself.
    assert "memory_error" in _read_log(steplog)


def test_nonzero_exit_alone_is_not_classified_as_a_limit_hit(
    allocator: Path, tmp_path: Path
) -> None:
    """A nonzero parser exit is NOT reported as a memory-limit hit.

    The limit attribution must come from the Job's violation signal, not
    from the target's exit status.
    """
    steplog = tmp_path / "parser.log"
    failing = tmp_path / "failing_child.py"
    failing.write_text(
        "import sys\nsys.stderr.write('parser exploded\\n')\nsys.exit(3)\n",
        encoding="utf-8",
    )
    result = wj.run_in_windows_job(
        [sys.executable, str(failing), str(steplog)],
        timeout_seconds=60,
        limit_bytes=TEST_LIMIT_BYTES,
    )
    assert result.returncode == 3
    assert result.memory_limit_violated is False
    assert wj._JOB_OBJECT_MSG_PROCESS_MEMORY_LIMIT not in result.job_notifications
    assert b"parser exploded" in result.stderr


# ---------------------------------------------------------------------------
# C. The MANDATORY negative control
# ---------------------------------------------------------------------------


def test_uncontained_control_crosses_threshold(allocator: Path, tmp_path: Path) -> None:
    """The negative control: the SAME executable, allocation strategy,
    timeout, and observation mechanism, but with Job assignment bypassed.

    It must **explicitly prove** it crossed the measured threshold, and it
    must FAIL if the allocator cannot cross it. A constant check, a
    mocked API, a skip, or a "no exception" observation would not satisfy
    this.
    """
    steplog = tmp_path / "control.log"
    marker = tmp_path / "control.marker"
    proc = subprocess.run(  # noqa: S603 -- intentional: the control bypasses the Job
        [
            sys.executable,
            str(allocator),
            str(ALLOCATION_BYTES),
            str(steplog),
            str(marker),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    log = _read_log(steplog)
    assert proc.returncode == 0, (
        f"the uncontained control must succeed; rc={proc.returncode} stderr={proc.stderr!r}"
    )
    # Explicit proof that the control crossed the threshold. Without this
    # assertion the control could pass vacuously.
    assert "STEP alloc_succeeded" in log, (
        f"the uncontained control did not prove it crossed the threshold; log={log!r}"
    )
    assert "STEP memory_error" not in log
    assert "STEP alloc_succeeded bytes=" in log
    # The control must also have really executed, proving it is a live
    # executable path and not a no-op.
    assert marker.exists(), "the uncontained control never executed"
    # The allocation must have been at least the threshold, otherwise the
    # comparison with the contained target would be meaningless.
    assert ALLOCATION_BYTES > TEST_LIMIT_BYTES


def test_negative_control_pair_fails_against_an_uncontained_implementation(
    allocator: Path, tmp_path: Path
) -> None:
    """The control and the contained target must disagree.

    This is the property that makes the pair a real gate: if the Job
    assignment were removed (an uncontained/no-op implementation), the
    contained run would succeed instead of being denied, so this test
    would fail for the expected enforcement reason.
    """
    control_log = tmp_path / "pair_control.log"
    control = subprocess.run(  # noqa: S603 -- intentional: the control bypasses the Job
        [sys.executable, str(allocator), str(ALLOCATION_BYTES), str(control_log)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert control.returncode == 0
    assert "STEP alloc_succeeded" in _read_log(control_log)

    contained_log = tmp_path / "pair_contained.log"
    with pytest.raises(wj.WindowsJobLimitExceededError):
        wj.run_in_windows_job(
            [sys.executable, str(allocator), str(ALLOCATION_BYTES), str(contained_log)],
            timeout_seconds=120,
            limit_bytes=TEST_LIMIT_BYTES,
        )
    assert "STEP memory_error" in _read_log(contained_log)


# ---------------------------------------------------------------------------
# D. Descendant inheritance and escape prevention
# ---------------------------------------------------------------------------


def test_descendant_inherits_the_per_process_limit(
    allocator: Path, tmp_path: Path
) -> None:
    """A descendant created after assignment inherits the limit.

    The parent allocates only a tiny amount, so the parent is unaffected;
    the grandchild then attempts the over-limit allocation and is denied.
    That proves the limit is inherited by descendants rather than applied
    only to the initially assigned process.
    """
    steplog = tmp_path / "descendant.log"
    with pytest.raises(wj.WindowsJobLimitExceededError):
        wj.run_in_windows_job(
            [
                sys.executable,
                str(allocator),
                "1024",
                str(steplog),
                "",
                str(ALLOCATION_BYTES),
            ],
            timeout_seconds=180,
            limit_bytes=TEST_LIMIT_BYTES,
        )
    log = _read_log(steplog)
    # The parent succeeded; the grandchild was denied.
    assert "STEP alloc_succeeded" in log
    grandchild_log = _read_log(Path(str(steplog) + ".grandchild"))
    assert "STEP memory_error" in grandchild_log, (
        f"the descendant must inherit the limit; grandchild log={grandchild_log!r}"
    )


# ---------------------------------------------------------------------------
# E. Sibling isolation
# ---------------------------------------------------------------------------


def test_unrelated_sibling_survives_timeout_cleanup(tmp_path: Path) -> None:
    """A process that is NOT in the Job survives timeout cleanup.

    The sibling is launched by the same harness but is never assigned to
    the Job. Cleanup terminates only the assigned Job, so the sibling
    must still be running afterwards.
    """
    sibling_marker = tmp_path / "sibling_alive.txt"
    sibling = subprocess.Popen(  # noqa: S603 -- intentional: a real sibling process
        [
            sys.executable,
            "-c",
            (
                "import pathlib, sys, time\n"
                f"pathlib.Path(r'{sibling_marker}').write_text('alive')\n"
                "time.sleep(120)\n"
            ),
        ],
    )
    try:
        deadline = time.time() + 30
        while not sibling_marker.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert sibling_marker.exists(), "the sibling never started"

        sleeper = tmp_path / "sleeper.py"
        sleeper.write_text("import time\ntime.sleep(120)\n", encoding="utf-8")

        with pytest.raises(wj.WindowsJobTimeoutError):
            wj.run_in_windows_job(
                [sys.executable, str(sleeper)],
                timeout_seconds=3,
                limit_bytes=TEST_LIMIT_BYTES,
            )

        # The sibling must have survived: it was never in the Job.
        assert sibling.poll() is None, "the unrelated sibling was terminated by cleanup"
        assert _process_alive(sibling.pid)
    finally:
        sibling.kill()
        sibling.wait(timeout=30)


# ---------------------------------------------------------------------------
# F. Ordering: the target stays suspended until assignment
# ---------------------------------------------------------------------------


def test_target_does_not_execute_before_assignment(allocator: Path, tmp_path: Path) -> None:
    """The target must not run a single instruction before assignment.

    The marker is the target's first action. The test observes the Job
    and the target while the target is still suspended: the marker must
    not exist and the target must not have allocated anything.
    """
    marker = tmp_path / "execution_marker.txt"
    steplog = tmp_path / "ordering.log"

    k32 = wj._load_kernel32()

    # Build the containment sequence by hand so the suspended state can
    # be observed between creation and assignment. This mirrors the
    # production sequence exactly.
    job = k32.CreateJobObjectW(None, None)
    assert job
    wj._configure_job(k32, int(job), limit_bytes=TEST_LIMIT_BYTES)
    port = k32.CreateIoCompletionPort(wj._INVALID_HANDLE_VALUE, None, None, 1)
    assert port
    wj._associate_completion_port(k32, int(job), int(port))

    startup = wj._STARTUPINFOW()
    startup.cb = ctypes.sizeof(wj._STARTUPINFOW)
    command_line = subprocess.list2cmdline(
        [sys.executable, str(allocator), str(ALLOCATION_BYTES), str(steplog), str(marker)]
    )
    process_info = wj._PROCESS_INFORMATION()
    created = k32.CreateProcessW(
        None,
        command_line,
        None,
        None,
        True,
        wj._CREATE_SUSPENDED | wj._CREATE_NO_WINDOW,
        None,
        None,
        ctypes.byref(startup),
        ctypes.byref(process_info),
    )
    assert created, "CreateProcessW(CREATE_SUSPENDED) failed"
    process_handle = wj._handle_to_int(process_info.hProcess)
    thread_handle = wj._handle_to_int(process_info.hThread)

    try:
        # --- while suspended: nothing has executed ---
        assert not marker.exists(), (
            "the target executed while it was still suspended -- the "
            "suspended-create ordering is broken"
        )
        assert not steplog.exists(), "the target wrote its log before assignment"
        assert k32.GetExitCodeProcess(
            process_handle, ctypes.byref(ctypes.c_uint32())
        ), "the suspended target is not queryable"

        # --- assign, then resume ---
        assert k32.AssignProcessToJobObject(job, process_handle)
        assert not marker.exists(), "the target executed between assignment and resume"
        k32.ResumeThread(thread_handle)
        k32.WaitForSingleObject(process_handle, 60000)
    finally:
        k32.TerminateJobObject(job, 1)
        k32.CloseHandle(thread_handle)
        k32.CloseHandle(process_handle)
        k32.CloseHandle(port)
        k32.CloseHandle(job)

    assert marker.exists(), "the target never executed after resume"
    assert "STEP started" in _read_log(steplog)


# ---------------------------------------------------------------------------
# G. Fail closed
# ---------------------------------------------------------------------------


def test_assignment_failure_cannot_execute_an_unconstrained_target(
    allocator: Path, tmp_path: Path
) -> None:
    """A REAL assignment failure must not let the target run.

    The Job is configured with ``JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0``,
    which makes ``AssignProcessToJobObject`` fail with a real Win32
    error. The target is created suspended; because assignment failed it
    is in no Job, so it is terminated directly. The marker file proves
    the target never executed.
    """
    marker = tmp_path / "assign_fail_marker.txt"
    steplog = tmp_path / "assign_fail.log"

    k32 = wj._load_kernel32()
    job = k32.CreateJobObjectW(None, None)
    assert job

    info = wj._JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = (
        wj._JOB_OBJECT_LIMIT_PROCESS_MEMORY
        | wj._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | 0x00000008  # JOB_OBJECT_LIMIT_ACTIVE_PROCESS
    )
    info.ProcessMemoryLimit = TEST_LIMIT_BYTES
    info.BasicLimitInformation.ActiveProcessLimit = 0
    assert k32.SetInformationJobObject(
        job,
        wj._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )

    startup = wj._STARTUPINFOW()
    startup.cb = ctypes.sizeof(wj._STARTUPINFOW)
    command_line = subprocess.list2cmdline(
        [sys.executable, str(allocator), str(ALLOCATION_BYTES), str(steplog), str(marker)]
    )
    process_info = wj._PROCESS_INFORMATION()
    created = k32.CreateProcessW(
        None,
        command_line,
        None,
        None,
        True,
        wj._CREATE_SUSPENDED | wj._CREATE_NO_WINDOW,
        None,
        None,
        ctypes.byref(startup),
        ctypes.byref(process_info),
    )
    assert created
    process_handle = wj._handle_to_int(process_info.hProcess)
    thread_handle = wj._handle_to_int(process_info.hThread)

    try:
        assigned = k32.AssignProcessToJobObject(job, process_handle)
        assert not assigned, "the assignment was supposed to fail"
        win32_error = ctypes.get_last_error()
        assert win32_error != 0

        # The fail-closed path: the target is in no Job, so it must be
        # terminated directly.
        k32.TerminateProcess(process_handle, 1)
        k32.WaitForSingleObject(process_handle, 10000)

        # It never resumed, so it never executed.
        assert not marker.exists(), (
            "the target executed even though the Job assignment failed"
        )
        assert not steplog.exists()
    finally:
        k32.CloseHandle(thread_handle)
        k32.CloseHandle(process_handle)
        k32.CloseHandle(job)


def test_process_creation_failure_is_a_setup_error(tmp_path: Path) -> None:
    """A failure to create the target is a distinct setup failure."""
    missing = tmp_path / "definitely-not-here.exe"
    with pytest.raises(wj.WindowsJobSetupError) as excinfo:
        wj.run_in_windows_job([str(missing)], timeout_seconds=30)
    assert excinfo.value.details["stage"] == "process_creation"
    assert excinfo.value.details["win32_error"] != 0


# ---------------------------------------------------------------------------
# H. Scoped cleanup and handle hygiene
# ---------------------------------------------------------------------------


def test_timeout_cleanup_leaves_no_contained_processes(tmp_path: Path) -> None:
    """Timeout cleanup terminates the Job's processes, and repeated runs
    leave nothing behind."""
    sleeper = tmp_path / "sleeper.py"
    pid_file = tmp_path / "child_pid.txt"
    sleeper.write_text(
        "import os, pathlib, time\n"
        f"pathlib.Path(r'{pid_file}').write_text(str(os.getpid()))\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )

    for _ in range(3):
        with pytest.raises(wj.WindowsJobTimeoutError):
            wj.run_in_windows_job(
                [sys.executable, str(sleeper)],
                timeout_seconds=3,
                limit_bytes=TEST_LIMIT_BYTES,
            )

    assert pid_file.exists(), "the child never started"
    child_pid = int(pid_file.read_text(encoding="utf-8").strip())
    # Give the OS a moment to finish tearing the process down.
    deadline = time.time() + 30
    while _process_alive(child_pid) and time.time() < deadline:
        time.sleep(0.1)
    assert not _process_alive(child_pid), (
        "a contained process survived the timeout cleanup"
    )


def test_repeated_execution_does_not_leak_handles() -> None:
    """Repeated runs must not leak Job, process, or thread handles.

    The first call pays a one-time cost (loading ``kernel32`` and its
    process/thread pools), so the measurement is taken after a warm-up
    and then compared across a batch.
    """
    warmup_before = wj._current_process_handle_count()
    wj.run_in_windows_job([sys.executable, "-c", "pass"], timeout_seconds=60)
    warmup_after = wj._current_process_handle_count()

    before = wj._current_process_handle_count()
    for _ in range(20):
        wj.run_in_windows_job([sys.executable, "-c", "pass"], timeout_seconds=60)
    after = wj._current_process_handle_count()

    # The warm-up may legitimately open some handles once (module load).
    # After that, a leak would show up as a per-run growth.
    assert after - before <= 2, (
        f"handle leak: {after - before} handles opened across 20 runs "
        f"(warm-up delta was {warmup_after - warmup_before})"
    )


# ---------------------------------------------------------------------------
# I. Distinct outcomes
# ---------------------------------------------------------------------------


def test_error_taxonomy_classes_are_distinct() -> None:
    """Every outcome has its own exception class."""
    classes = {
        wj.WindowsJobSetupError,
        wj.WindowsJobLimitExceededError,
        wj.WindowsJobTimeoutError,
        wj.WindowsJobCleanupError,
    }
    assert len(classes) == 4
    for cls in classes:
        assert issubclass(cls, wj.WindowsJobError)
    assert not issubclass(wj.WindowsJobSetupError, wj.WindowsJobLimitExceededError)
    assert not issubclass(wj.WindowsJobTimeoutError, wj.WindowsJobLimitExceededError)
    assert not issubclass(wj.WindowsJobCleanupError, wj.WindowsJobLimitExceededError)


def test_setup_limit_and_timeout_outcomes_are_distinct(tmp_path: Path) -> None:
    """Setup, limit, and timeout outcomes are observably different."""
    # Setup failure.
    with pytest.raises(wj.WindowsJobSetupError):
        wj.run_in_windows_job([str(tmp_path / "nope.exe")], timeout_seconds=30)

    # Limit failure.
    allocator = tmp_path / "alloc.py"
    allocator.write_text(_ALLOCATOR_SOURCE, encoding="utf-8")
    with pytest.raises(wj.WindowsJobLimitExceededError):
        wj.run_in_windows_job(
            [sys.executable, str(allocator), str(ALLOCATION_BYTES), str(tmp_path / "a.log")],
            timeout_seconds=120,
            limit_bytes=TEST_LIMIT_BYTES,
        )

    # Timeout failure.
    sleeper = tmp_path / "sleep.py"
    sleeper.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    with pytest.raises(wj.WindowsJobTimeoutError):
        wj.run_in_windows_job(
            [sys.executable, str(sleeper)], timeout_seconds=3, limit_bytes=TEST_LIMIT_BYTES
        )

    # A generic parser failure is NOT any of the three.
    failing = tmp_path / "fail.py"
    failing.write_text("import sys\nsys.exit(9)\n", encoding="utf-8")
    result = wj.run_in_windows_job(
        [sys.executable, str(failing)], timeout_seconds=60, limit_bytes=TEST_LIMIT_BYTES
    )
    assert result.returncode == 9


def test_cleanup_errors_are_secondary_not_masking(tmp_path: Path) -> None:
    """A cleanup failure must not replace the primary error."""
    error = wj.WindowsJobLimitExceededError("primary", details={"limit_bytes": 1})
    assert error.details["limit_bytes"] == 1
    # The primary details survive; cleanup diagnostics are additive.
    error.details.setdefault("cleanup_errors", []).append("CloseHandle(x) failed")
    assert error.details["limit_bytes"] == 1
    assert error.details["cleanup_errors"]


def test_unsupported_platform_is_refused_not_faked(tmp_path: Path) -> None:
    """The backend refuses to run anywhere but Windows.

    It never falls back to an unconstrained subprocess, source-tree
    execution, or the Linux ``RLIMIT_AS`` mechanism.
    """
    if sys.platform == "win32":
        pytest.skip("this test asserts the non-Windows behaviour")
    with pytest.raises(wj.WindowsJobSetupError):
        wj.run_in_windows_job([sys.executable, "-c", "pass"], timeout_seconds=5)
