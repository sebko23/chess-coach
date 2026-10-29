# BBF-FU-22-B2-windows-job-object — real Windows Job Object enforcement

**Date:** 2026-10-28
**Finding:** FU-22 (A-F11 property 4 — the 2 GB memory cap)
**Status:** implements B2; closes FU-22 when the Windows CI job is green
**Predecessor:** `BBF-FU-22-windows-contract-correction` (B1, PR #187, merged `5a5a6760`)

---

## 1. What B1 left behind

B1 corrected FU-22's *claim*, not its *implementation*. The B1 record is
preserved in `docs/16_audit/OPEN-FOLLOWUPS.md` under the FU-22 entry and
in the Resolved section; this brief does not rewrite it.

B1 established:

- The Linux cap (`resource.setrlimit(RLIMIT_AS, (2 GiB, 2 GiB))` in a
  `preexec_fn`) is real and directly tested.
- The Linux limit is **per-process**, inherited *independently* by
  descendants — **not** an aggregate process-tree memory budget.
- `resource` is Unix-only and CPython rejects `preexec_fn` on Windows
  (`ValueError: preexec_fn is not supported on Windows platforms`), so
  `set_rlimit_as_preexec` was a no-op there.
- Because the cap could not be applied on Windows, `run_pdftoppm_in_subprocess`
  **refused** on that platform: `ensure_memory_cap_supported()` raised a
  typed `UnsupportedParserPlatformError` (HTTP 501,
  `internal.not_implemented`) **before** any parser process was spawned.
  Windows PDF parsing was therefore *deliberately unsupported* — honest,
  but not implemented.

B1 listed B2's obligations explicitly: real Job Object enforcement, an
explicitly declared dependency if one were used, a Windows CI job, and
executable Windows enforcement tests including a negative control that
distinguishes a real enforced limit from a constant.

## 2. B2's threat model

The attacker controls the PDF bytes. Poppler may allocate without bound
on a pathological input, and it may spawn descendants. The property
A-F11 requires is a **memory ceiling on the parser process tree**.

B2's threat model is specifically the **race** that a naive
implementation introduces. If the target is launched normally and
assigned to a Job afterwards, the target may already have:

- allocated memory beyond the intended ceiling, and
- created descendants that are outside the Job and therefore unconstrained.

The window between "process exists" and "process is in a Job" is exactly
the window an attacker needs. B2 closes it by never letting the target
run a single instruction before Job membership and the limit are
established.

## 3. The API and dependency choice

**Chosen: the standard-library `ctypes` binding to `kernel32`. No
`pywin32`. No dependency change. `uv.lock` untouched.**

The directive permits `pywin32` only if it exposes the complete
low-level suspended-create → configure → assign → terminate → resume
sequence, and warns against choosing it "merely for convenience if it
prevents explicit suspended-create-to-assign-to-resume control".

`ctypes` was chosen because:

1. **The ordering is directly expressible and auditable.** Every step
   is one named function call in one function body, in the required
   order, visible in a diff.
2. **Exact prototypes and structure sizes** are pinned in the module and
   asserted by the test suite (`ctypes.sizeof(...) == 64 / 48 / 144`).
3. **Explicit handle ownership.** The module keeps a `_Handles` record
   and closes every handle exactly once in a `finally` block; a close
   failure becomes a secondary diagnostic, never a masked primary error.
4. **Checked return values with captured Win32 error codes.**
   `ctypes.get_last_error()` is captured immediately after each failing
   call and travels in the exception's `details`.
5. **The primary-thread handle is retained**, so the target can be
   resumed only after assignment.

`pywin32` would have added a platform-specific dependency, lockfile
churn, and a separate install-proof obligation, while its high-level
wrappers would obscure the very ordering this BBF must prove.

**Dependency/install proof:** because the backend is stdlib-only, the
installed environment needs nothing beyond CPython. The Windows CI job
installs the package with `pip install -e '.[dev]'` and then asserts
that the *production* module reports `WINDOWS_JOB_SUPPORTED`, the 2 GiB
limit, and `MEMORY_CAP_SUPPORTED`. `pyproject.toml`, `uv.lock`, the
build backend, and the entry points are all unchanged.

### Win32 call sequence (production path)

```
1. CreateFileW x3   -- inheritable stdin/stdout/stderr handles
2. CreateJobObjectW
3. SetInformationJobObject(hJob, JobObjectExtendedLimitInformation=9,
                           LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY
                                        | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
                           ProcessMemoryLimit = 2 GiB, JobMemoryLimit = 0)
4. CreateIoCompletionPort + SetInformationJobObject(hJob,
                           JobObjectAssociateCompletionPortInformation=7)
5. CreateProcessW(..., CREATE_SUSPENDED | CREATE_NO_WINDOW, ...)
6. AssignProcessToJobObject(hJob, hProcess)
7. ResumeThread(hThread)                      <-- first moment the target runs
8. WaitForSingleObject(hProcess, timeout)
9. GetQueuedCompletionStatus drain + QueryInformationJobObject
10. finally: CloseHandle(thread, process, stdio, port, job)
```

Step 3 precedes step 6, and step 6 precedes step 7. The limit is
therefore in force before the target can allocate, execute user code, or
create descendants.

## 4. Limit semantics: per-process, never aggregate

The production limit uses the Job Object **per-process** memory limit
field:

- `LimitFlags |= JOB_OBJECT_LIMIT_PROCESS_MEMORY` (`0x00000100`)
- `ProcessMemoryLimit = 2 * 1024**3` (exactly 2 GiB)
- `JobMemoryLimit = 0` and **`JOB_OBJECT_LIMIT_JOB_MEMORY` (`0x00000200`)
  is never set**

The aggregate tree budget is *disabled*, not merely unused. The test
suite reads the Job's limits back through
`QueryInformationJobObject` and asserts:

- `flags & JOB_OBJECT_LIMIT_PROCESS_MEMORY` is set,
- `flags & JOB_OBJECT_LIMIT_JOB_MEMORY` is **not** set,
- `ProcessMemoryLimit == 2 * 1024**3`,
- `JobMemoryLimit == 0`.

Breakaway (`JOB_OBJECT_LIMIT_BREAKAWAY_OK` and
`JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK`) is never enabled, so
descendants inherit Job membership and cannot escape it.

**The guarantee is a per-process ceiling inherited by descendants. It is
NOT a 2 GiB aggregate process-tree memory budget.** A tree of four
processes may use up to 4 × 2 GiB in total; what the Job forbids is any
*single* process exceeding 2 GiB. This mirrors the Linux semantics
exactly: `RLIMIT_AS` is likewise per-process with independent
inheritance.

## 5. Fail-closed guarantee

No failure path can produce an unconstrained or resumed target:

| Failure | Response | Target state |
|---|---|---|
| Job creation | raise `WindowsJobSetupError` | never created |
| Limit configuration | raise `WindowsJobSetupError` | suspended; terminated directly |
| Process creation | raise `WindowsJobSetupError` | never created |
| **Assignment** | raise `WindowsJobSetupError` | suspended, **in no Job** → `TerminateProcess` |
| **Resume** | raise `WindowsJobSetupError` | **in the Job** → `TerminateJobObject` |

The assignment-failure case deserves its own note: the still-suspended
target is in no Job, so `TerminateJobObject` **cannot reach it**. It is
terminated directly with `TerminateProcess`. Because it never resumed,
it cannot have created descendants. (This was verified empirically: an
abandoned unassigned suspended child lingers holding its stdio handles
unless terminated directly.)

There is **no** fallback on Windows to `preexec_fn`, to source-tree
execution, or to the Linux `RLIMIT_AS` mechanism.

## 6. Cleanup scope

Timeout and failure cleanup terminate **only the assigned Job**, via
`TerminateJobObject`. The implementation never kills by PID list,
process name, or ancestry guesswork, so an unrelated sibling process is
never terminated. The test suite proves this by launching a sibling from
the same harness, forcing a timeout, and asserting the sibling is still
running afterwards.

Handles are closed deterministically in `finally` blocks. A cleanup
failure is recorded as secondary diagnostic context
(`details["cleanup_errors"]`) and never replaces the primary parser,
timeout, or containment error.

Measured handle hygiene: a warm-up call costs 9 handles (loading
`kernel32` and its process/thread pools); after that, **20 consecutive
runs showed a handle-count delta of 0**, and 60 runs showed no growth.

## 7. Error taxonomy and route mapping

| Outcome | Exception | HTTP | Notes |
|---|---|---|---|
| Platform with no mechanism | `UnsupportedParserPlatformError` | 501 | `internal.not_implemented`; unchanged from B1 |
| Job creation / limit config / process creation / assignment / resume | `WindowsJobSetupError` | **500** | internal containment failure; target never resumed |
| Per-process limit violation | `WindowsJobLimitExceededError` | **422** | the A-F11 property-4 hit on Windows |
| Timeout | `WindowsJobTimeoutError` | **504** | Job terminated and drained first |
| Parser nonzero exit | `RuntimeError` | 422 | the existing parser-failure semantics |
| Generic parser failure | `RuntimeError` | 422 | unchanged |
| Cleanup failure | `WindowsJobCleanupError` | — | **secondary**; never masks the primary |

The 500 for a setup failure is what keeps it distinguishable: a
containment-setup failure is an internal fault, not a client error, and
it must not degrade into an "indistinguishable generic 422".

## 8. Limit-hit attribution

Attribution is deliberately conservative, because a limit hit and a
generic parser failure must not be confused.

1. An I/O completion port is associated with the Job **before
   assignment**, so job notifications are delivered for the target's whole
   lifetime.
2. The **primary** attributable signal is the job notification for a
   per-process memory limit violation.
3. The Job's limit-violation information (the class-8 query) is
   **secondary** evidence.
4. The target's own allocation failure (`MemoryError` in the child) is
   **corroborating** evidence only.
5. **A nonzero parser exit alone is never classified as a limit hit.**
   The test `test_nonzero_exit_alone_is_not_classified_as_a_limit_hit`
   pins this: a child that exits 3 with a parser error is reported as a
   plain parser failure, with no memory-limit notification present.
6. A memory-limit outcome is claimed only when the configured Job limit
   and an attributable violation are tied together — the error's
   `details` carry `limit_bytes`, `limit_field`,
   `limit_flag`, and the observed notifications.

### Measured notification ids (host limitation worth recording)

The job-notification ids used for attribution were **measured on a real
Windows host**, not copied from SDK headers:

| Condition | Notification id |
|---|---|
| Per-process memory limit violation | `0x09` |
| Aggregate (Job memory) limit violation | `0x0A` |
| Clean run | neither |
| No memory limit configured | neither |

These ids do **not** match the values published in some SDK headers
(which document `JOB_OBJECT_MSG_PROCESS_MEMORY_LIMIT = 0x08` and
`JOB_OBJECT_MSG_JOB_MEMORY_LIMIT = 0x09`). The measured mapping was
established by running four isolated cases on a real host with real
Win32 calls and a fresh Job and completion port per case:

- per-process limit only + over-limit allocation → `0x09`
- aggregate limit only + over-limit allocation → `0x0A`
- per-process limit + small allocation → neither
- no memory limit + over-limit allocation → neither

Because the ids were measured rather than assumed, they are pinned in
`windows_job.py` with a comment explaining the discrepancy. **This is a
platform/SDK-version observation, not a portability guarantee**: the
backend keys the attribution off the *measured* per-process id, and the
test suite asserts the measured behaviour rather than a copied
constant. If a future Windows build renumbers these ids, the
attribution test will fail loudly rather than silently mis-classify.

Two further host limitations were measured and are recorded here:

- `QueryInformationJobObject` with
  `JobObjectLimitViolationInformation` requires a **96-byte** buffer on
  this platform (the SDK-documented struct is smaller); the module uses
  96 and the size is asserted in the test suite.
- `PeakProcessMemoryUsed` does **not** reveal a violation (it read
  8 249 344 against a 67 108 864 limit after a violation), so it is not
  used as an attribution signal.

## 9. Real Windows CI

One dedicated `windows-latest` job was added to `.github/workflows/smoke.yml`
(`windows-job-enforcement`). It is the **only** Windows runner in the
workflow; no unrelated OS matrix was added and the existing Linux jobs
are untouched, so the Linux `RLIMIT_AS` job continues to protect the
Linux half.

The job:

1. checks out the repository,
2. sets up Python 3.11,
3. installs the package with `pip install -e '.[dev]'`,
4. runs `pytest tests/windows/test_windows_job_enforcement.py`,
5. asserts the production module reports the 2 GiB limit and that
   `MEMORY_CAP_SUPPORTED` is true on Windows,
6. asserts the route maps the Job error taxonomy and that the runner
   reaches the Job backend.

The test file is collected **explicitly** rather than through a glob, so
a rename or move fails the job loudly instead of silently unenforcing
the suite.

## 10. The Windows test suite

`tests/windows/test_windows_job_enforcement.py` — 18 real tests, 1
platform skip. Every test executes real Win32 calls on a real Windows
runner; there is no mocked Job API and no source-tree-only proof.

| Property | Test |
|---|---|
| Production limit is exactly 2 GiB | `test_production_limit_is_2gib` |
| Per-process field used; aggregate disabled | `test_limit_uses_per_process_field_not_aggregate` |
| Breakaway never enabled | `test_breakaway_is_never_enabled` |
| Structure sizes match the SDK | `test_structure_sizes_match_the_win32_sdk` |
| **Target enforcement** (kernel denies) | `test_contained_target_is_denied_at_the_same_threshold` |
| Nonzero exit ≠ limit hit | `test_nonzero_exit_alone_is_not_classified_as_a_limit_hit` |
| **Negative control crosses the threshold** | `test_uncontained_control_crosses_threshold` |
| Control/contained pair disagrees | `test_negative_control_pair_fails_against_an_uncontained_implementation` |
| **Descendant inheritance** | `test_descendant_inherits_the_per_process_limit` |
| **Sibling survival** | `test_unrelated_sibling_survives_timeout_cleanup` |
| **Suspended until assignment** | `test_target_does_not_execute_before_assignment` |
| **Fail-closed assignment failure** | `test_assignment_failure_cannot_execute_an_unconstrained_target` |
| Process-creation failure is a setup error | `test_process_creation_failure_is_a_setup_error` |
| Scoped cleanup, no leaked processes | `test_timeout_cleanup_leaves_no_contained_processes` |
| **Handle hygiene** | `test_repeated_execution_does_not_leak_handles` |
| Distinct outcome classes | `test_error_taxonomy_classes_are_distinct` |
| Setup/limit/timeout/parser distinct | `test_setup_limit_and_timeout_outcomes_are_distinct` |
| Cleanup errors do not mask | `test_cleanup_errors_are_secondary_not_masking` |
| Non-Windows refuses, never fakes | `test_unsupported_platform_is_refused_not_faked` |

### The mandatory negative control

`test_uncontained_control_crosses_threshold` is a **real executable
path** that bypasses Job creation and assignment while using the same
executable, the same allocation strategy, the same timeout, and the same
observation mechanism:

- it runs the identical allocator helper as the contained target,
- it allocates the identical 512 MiB against the identical 64 MiB
  threshold,
- it uses the identical step-log observation,
- it asserts `STEP alloc_succeeded` is present — **explicit proof that it
  crossed the measured threshold**,
- it asserts `STEP memory_error` is absent,
- it asserts the control's marker file exists, proving the control
  really executed rather than being a no-op,
- it fails if the allocator cannot cross the threshold.

The paired test
`test_negative_control_pair_fails_against_an_uncontained_implementation`
runs both and requires them to disagree.

### The gate is not vacuous — measured

The gate was verified against a **real uncontained implementation**: the
production module was copied into an isolated tree and its
`run_in_windows_job` replaced with a direct, uncontained
`subprocess.Popen` launch (no Job at all). The suite was then run
against it.

**Result: 5 failures, 13 passed** — the gate fails against the
uncontained implementation, for the expected enforcement reasons:

- `test_contained_target_is_denied_at_the_same_threshold`
- `test_negative_control_pair_fails_against_an_uncontained_implementation`
- `test_descendant_inherits_the_per_process_limit`
- `test_process_creation_failure_is_a_setup_error`
- `test_setup_limit_and_timeout_outcomes_are_distinct`

No skip, no missing selector, no harness import error, no pytest exit 5,
and no constant-only assertion was involved: the failures are the
enforcement assertions themselves.

## 11. Linux parity — unchanged

The Linux path is byte-for-byte unchanged in behaviour:

- `set_rlimit_as_preexec` still applies `RLIMIT_AS` at 2 GiB in a
  `preexec_fn`;
- `test_memory_cap_is_enforced_not_merely_declared` still proves the
  kernel refuses an over-limit reservation;
- `test_descendant_inherits_memory_cap_independently` still proves
  inheritance **and** independence;
- the Linux branch of `run_pdftoppm_in_subprocess` is untouched; the
  Windows branch is an `if WINDOWS_JOB_SUPPORTED:` dispatch in front of
  it.

Two B1-era tests were updated because B2 intentionally changes the
contract they pinned, and one wiring test was scoped to the branch it
actually measures:

- `test_windows_pdf_parsing_is_unsupported_and_spawns_no_process` →
  renamed `test_uncappable_platform_refuses_and_spawns_no_process` and
  now simulates a platform with **neither** mechanism (it previously
  simulated Windows, which now has one). The refusal contract — typed
  error, 501, `internal.not_implemented`, no process spawned — is
  unchanged.
- `test_linux_cap_contract_is_per_process_not_an_aggregate_tree_budget`
  now asserts the mechanism string **per platform** (the semantics are
  identical: per-process, not aggregate).
- `test_network_isolation_is_wired_into_the_popen_preexec` now forces
  the Linux branch, because it measures the composed `preexec_fn` handed
  to `subprocess.Popen` — which is the Linux mechanism. The Windows
  mechanism is proved by the Windows suite.

## 12. Documentation corrections

`docs/08_security/security-strategy.md` §A-F11 property 4 previously
stated that "Windows: PDF parsing is UNSUPPORTED" and that "there is no
Job Object memory cap in this codebase". Both statements are now false
and were corrected, with B1's superseded wording preserved in place as
labelled history per the repository's documentation-truthfulness
convention.

## 13. Files changed

| File | Change |
|---|---|
| `services/chess_coach/pdf_ocr/windows_job.py` | **new** — the ctypes Job Object backend |
| `services/chess_coach/pdf_ocr/subprocess_runner.py` | Windows dispatch + platform-aware capability + prose |
| `services/chess_coach/gateway/routes/pdf_ingest.py` | route-level mapping for the new outcomes |
| `tests/windows/test_windows_job_enforcement.py` | **new** — 18 real Windows tests |
| `tests/unit/test_subprocess_runner.py` | B1-era contract updated for B2 |
| `tests/unit/test_pdf_ingest_security.py` | B1-era contract updated for B2 |
| `.github/workflows/smoke.yml` | **new** `windows-latest` job |
| `docs/08_security/security-strategy.md` | §A-F11 property-4 prose corrected |
| `docs/16_audit/OPEN-FOLLOWUPS.md` | FU-22 closure |
| `docs/16_audit/BBF-FU-22-B2-windows-job-object.md` | **new** — this brief |

**Unchanged:** `pyproject.toml`, `uv.lock`, dependencies, entry points,
the build backend, the PyInstaller spec, FU-20, and the protected
FU-22/FU-35/FU-38 pointer values.

## 14. Residual risks and platform limitations

1. **The notification ids are measured, not documented.** They are
   pinned from measurement on the CI platform. A future Windows build
   that renumbers them would break attribution — visibly, via the
   attribution test, rather than silently.
2. **The class-8 violation-information buffer is 96 bytes** on the
   measured platform, not the SDK-documented struct size. The size is
   asserted in the test suite.
3. **The Windows CI job does not install poppler.** The job proves the
   *containment mechanism* end to end (a real target, a real
   allocation, a real kernel denial). A full `pdftoppm` round trip on
   Windows would additionally require a poppler build, which is a
   separate dependency decision and is not needed to establish A-F11
   property 4 — the property is about the memory ceiling on the parser
   process, which the Job enforces regardless of which executable runs
   inside it.
4. **Network isolation (A-F11 property 2) is still not enforced on
   Windows.** That is FU-20's subject, explicitly out of scope here.
5. **Read-only filesystem (A-F11 property 3) is still not enforced on
   Windows.** That is FU-21's subject, explicitly out of scope here.
6. **The per-process limit is a committed-memory ceiling, not an
   address-space ceiling.** The Linux `RLIMIT_AS` mechanism caps virtual
   address space. The two are not identical in what they bound; both are
   per-process ceilings inherited by descendants, which is the property
   A-F11 requires.
