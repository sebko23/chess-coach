# BBF-FU-22-windows-contract-correction — A-F11 property 4: make the Windows cap contract truthful

**Sprint intent:** Correct the A-F11 property-4 (2 GB memory cap) contract. Linux enforcement
exists and is now directly tested; the Windows half was never implemented and was described as
if it were. This BBF makes Windows PDF parsing **deliberately unsupported** (a typed, distinct
result instead of an incidental 422), states the Linux limit precisely as a per-process
address-space limit rather than an aggregate process-tree budget, and corrects every
current-state claim that `win32job` is already in use.

**Status:** B1 of the B1/B2 split selected by the FU-20/FU-22 threat-model review.
**Tree:** `bcb70d884fed8397e3e640b25695c017cc5f029f` (base), branch `bbf-fu22-windows-contract-correction`.
**Author identity:** Sebastian Wasielewski `<lesson@o2.pl>`, co-authored by Hermes Agent.

---

## 1. Finding identity (corrected)

The threat-model review found a **naming** problem and a **truthfulness** problem.

**Naming.** The 2 GB cap is **FU-22** (A-F11 property 4), not FU-20. FU-20 is A-F11 property 2
(network isolation) and is `PARTIALLY RESOLVED` since PR #163/#164 (`4c11159c` / `fa0bfd73`,
2026-10-18). **FU-20 is not touched by this BBF.**

**Truthfulness.** FU-22 was marked `RESOLVED 2026-10-16 via squash-merge of PR #145`
(`ae543ea8`). That status was accurate for **Linux** but overstated the property, because:

1. **The Windows half was never implemented.** `resource` is a Unix-only stdlib module and
   CPython rejects `preexec_fn` on Windows, so `set_rlimit_as_preexec` returns a no-op there.
2. **Windows PDF parsing was broken, not merely uncapped.** `subprocess.Popen(preexec_fn=...)`
   raises `ValueError: preexec_fn is not supported on Windows platforms` *before* `pdftoppm`
   starts, and the route's `except Exception` converted that internal configuration failure into
   an incidental **422** — indistinguishable from a malformed PDF or a generic parser failure.
3. **The "2 GB cap" test asserted a constant and a callable, not enforcement.**
   `test_subprocess_respects_2gb_memory_cap` checked `MEM_CAP_BYTES == 2 GiB` and
   `callable(preexec)`; both hold even if no limit is applied at all. Its own docstring says the
   end-to-end enforcement test was *"intentionally NOT included here"*.

**And two audit briefs asserted something false.** `docs/16_audit/BBF-FU-21-windows-scope.md`
§1.1 and §4, and `docs/16_audit/BBF-FU-20-impl-windows.md` §1, stated that `win32job` was
*"already used in `subprocess_runner.py`"*. It was not:

```
$ git grep -n -E '^\s*(import|from)\s+win32job' -- '*.py'
(no matches — exit 1)
$ git grep -n 'win32job' -- '*.py'
services/chess_coach/pdf_ocr/subprocess_runner.py:97:  # `pywin32` and the `win32job` module, which is
services/chess_coach/pdf_ocr/subprocess_runner.py:169: # The `win32job` module exposes:
```

Both occurrences are **comments**. `pywin32` is **not a declared dependency**
(`git grep -n pywin32 -- pyproject.toml` → exit 1); it appears in `uv.lock` only as a
transitive entry. `BBF-FU-20-impl-windows.md` also contradicted itself: §1 said the cap was
*"already used by FU-22-impl"* while §5 of the same file said it *"is still not implemented"*.
**§5 was correct; §1 was false.**

The authoritative implementation brief, `docs/16_audit/BBF-FU-22-impl-A-F11-memory-cap.md`
§"The Linux-vs-Windows split", was **honest** and is unchanged by this BBF.

---

## 2. The corrected contract

### Linux (enforced; unchanged mechanism)

> The PDF parser subprocess is subject to a hard **2 GiB `RLIMIT_AS` virtual-address-space
> limit**, applied **per process** and established before the parser's first instruction.
> Descendants **inherit the limit independently** — each descendant receives its **own** 2 GiB
> allowance. The limit is **not an aggregate process-tree memory budget**: there is no single
> 2 GiB pool shared across the tree.

### Windows (unsupported by design)

> Windows PDF parsing is **UNSUPPORTED**. The A-F11 cap cannot be enforced there — the
> mechanism is Unix-only and CPython rejects `preexec_fn` outright. Rather than launch an
> uncapped parser, the gateway **refuses**: `ensure_memory_cap_supported()` raises a typed
> `UnsupportedParserPlatformError` (**HTTP 501**, ADR-0002 code **`internal.not_implemented`**,
> `retriable=False`) **before any parser process is spawned**.

### Distinguishability

| Outcome | Status | Code |
|---|---|---|
| Malformed input (no `%PDF-` header) | 400 | `client.bad_request` |
| Oversized upload (> 50 MB) | 413 | `client.payload_too_large` |
| **Unsupported platform (this BBF)** | **501** | **`internal.not_implemented`** |
| Missing tool / generic parser failure | 422 | `client.validation_error` |
| Timeout (5-minute budget) | 504 | — |
| Cap hit (Linux) | 422 | `client.validation_error` |

The 501 is a deliberate, documented result — not an incidental consequence of an internal
configuration error.

---

## 3. Code changes

### `services/chess_coach/pdf_ocr/subprocess_runner.py`

| Change | Detail |
|---|---|
| `MEMORY_CAP_SUPPORTED` | `bool = HOST_PLATFORM != "win32"` — the capability decision, in one place |
| `HOST_PLATFORM` | module-level platform identifier, so tests can simulate an uncappable platform **without** mutating the process-wide `sys.platform` |
| `MEMORY_CAP_MECHANISM` | `"RLIMIT_AS via preexec_fn"` — surfaced in the error details so the client can see what is missing |
| `UnsupportedParserPlatformError` | subclass of `NotImplementedYetError` → HTTP 501, code `internal.not_implemented`, `retriable=False`, `details={platform, required_mechanism, cap_bytes, resource}` |
| `ensure_memory_cap_supported()` | raises the typed error when the cap cannot be enforced |
| **Call site** | `run_pdftoppm_in_subprocess` calls the guard **as its first action**, before `subprocess.Popen` — so the unsupported path never starts a process |
| Module docstring | corrected: platform support, the per-process (not aggregate) semantics, and the fact that the Windows no-op callable is unreachable because CPython rejects `preexec_fn` |

### `services/chess_coach/gateway/routes/pdf_ingest.py`

| Change | Detail |
|---|---|
| Import | `UnsupportedParserPlatformError` alongside `run_pdftoppm_in_subprocess` |
| New `except` clause | `except UnsupportedParserPlatformError: raise` — placed **before** the `(MemoryError, OSError)` clause so the typed error is **re-raised** to the gateway's central handler (ADR-0002) instead of being flattened into the catch-all's 422 |

No change to the 2 GB constant, to the Linux mechanism, to the timeout, or to any other route
behaviour.

---

## 4. Test changes

### `tests/unit/test_subprocess_runner.py` (5 new tests)

| Test | What it proves |
|---|---|
| `test_memory_cap_is_enforced_not_merely_declared` | Applies a real `RLIMIT_AS` and observes the kernel **refuse** an over-limit allocation. A constant-and-callable check would pass while enforcement was broken. |
| `test_descendant_inherits_memory_cap_independently` | A grandchild **inherits** the limit (its allocation is refused) **and** gets its **own** allowance (parent + grandchild each allocate a share, together exceeding the cap). This is the proof that the limit is **per-process, not an aggregate tree budget**. |
| `test_windows_pdf_parsing_is_unsupported_and_spawns_no_process` | The deliberate typed result, its ADR-0002 values, and that `subprocess.Popen` is **never called**. |
| `test_ensure_memory_cap_supported_raises_on_unsupported_platform` | The guard is the single gate, and raises the typed error. |
| `test_unsupported_platform_error_is_distinguishable_from_other_outcomes` | 501 collides with none of 400 / 404 / 413 / 422 / 504. |

### `tests/unit/test_pdf_ingest_security.py` (5 new tests)

| Test | What it proves |
|---|---|
| `test_unsupported_platform_returns_501_not_422` | **Route level**: the client receives 501 / `internal.not_implemented` and no parser process starts. |
| `test_unsupported_platform_is_distinct_from_other_pdf_outcomes` | The 501 differs from the 400 (malformed) and from the generic-failure status. |
| `test_windows_unsupported_path_never_spawns_a_parser` | Subprocess level: the refusal happens at the runner boundary. |
| `test_windows_unsupported_result_carries_the_established_contract` | 501 / `internal.not_implemented` / `retriable=False`. |
| `test_linux_cap_contract_is_per_process_not_an_aggregate_tree_budget` | The contract is pinned in **code and prose**. |

### Measured Linux enforcement

```
grandchild_limit 536870912
grandchild_alloc REFUSED
child_alloc SUCCEEDED
```

`grandchild_alloc REFUSED` = the descendant is capped (inheritance works).
`child_alloc SUCCEEDED` alongside it = the parent and the descendant each held their own
allowance simultaneously (independence — no aggregate pool).

Two implementation notes, because `RLIMIT_AS` caps **address space**, not resident memory:

- The probe uses `mmap` rather than `bytearray`. An `mmap` reservation over the cap fails
  deterministically with `MemoryError`/`OSError` (ENOMEM) without committing physical memory,
  whereas a large `bytearray` may be OOM-killed instead — a different, less precise signal.
- The child is a **fresh `exec`'d interpreter**, and the grandchild is **forked** from it. A
  forked child inherits the parent's *mappings*, so in a full-suite run the pytest parent's
  footprint alone can exceed the cap and make the test fail for the wrong reason; a fresh
  interpreter has a small, predictable footprint. The grandchild is forked (not exec'd) so it
  inherits the limit without needing to start another interpreter *inside* the cap — the
  measurement is whether the inherited limit is enforced for a descendant.

### A pre-existing test that this BBF had to adjust

`test_network_isolation_is_wired_into_the_popen_preexec` calls `run_pdftoppm_in_subprocess`
directly and asserts that the composed pre-exec hook runs the three isolation callbacks in
order. It replaces `subprocess.Popen` with a fake so it can run on Windows. Because the guard
now fires *before* `Popen`, the test reached the new refusal instead of the `RuntimeError` it
expected. The test now simulates a **supported** platform
(`MEMORY_CAP_SUPPORTED = True`, restored in its `finally` block) so it still reaches the
`Popen` call it is asserting. The Windows refusal is covered separately by
`test_windows_unsupported_path_never_spawns_a_parser`. No production behaviour changed.

### Test results

- Windows host (`tests/unit/`, CI-equivalent ignores applied): **548 passed, 11 skipped, 0 failed**
- Linux container (`tests/unit/`, same ignores): **533 passed, 5 skipped, 0 failed**
- Linux container (`tests/unit/test_subprocess_runner.py` + `tests/unit/test_pdf_ingest_security.py`): **33 passed, 5 skipped**
- `ruff` (whole repo): **All checks passed**
- `git diff --check` (staged): **clean**
- `verify_commit_refs` (commit body + PR body): **exit 0**
- `verify_bbb_flip_rules` (base `bcb70d8`, commit body + PR body): **exit 0** — `OK: BBF flip rules verified (sha-ancestry (2 SHA(s)))`

Two pre-existing failure sets are unrelated to this BBF and are excluded from the Linux numbers
above: `tests/unit/test_verify_bbf_flip_rules.py` (12 failures — these tests need a `git`
binary, which the Linux container lacks; on the real Windows host the same file passes) and
`tests/unit/test_lint_utf8_guard.py` (3 failures — same cause).

### The tests fail against the pre-B1 implementation

Run against a scratch copy with `subprocess_runner.py` and `pdf_ingest.py` restored to
`bcb70d8`, the new tests fail: the pre-B1 code reaches `subprocess.Popen(preexec_fn=...)`, has
CPython raise `ValueError`, and surfaces an incidental 422 instead of the deliberate typed 501.
The negative-test harness asserts the restored blobs contain neither `ensure_memory_cap_supported`
nor `UnsupportedParserPlatformError`, so it cannot silently test the wrong tree.

### A CI-coverage note (important)

`tests/integration/test_pdf_import.py` is explicitly `--ignore`d by the CI job
(`.github/workflows/smoke.yml:181`), so route-level tests placed there would **never run in
CI**. The route-level tests are therefore in `tests/unit/test_pdf_ingest_security.py`, which the
`pytest-cov` job does run (`smoke.yml:651`, `tests/unit/`).

### A dual-import hazard worth recording

The package tree is importable under **two** dotted paths — `chess_coach.pdf_ocr...` and
`services.chess_coach.pdf_ocr...` — and **both can be loaded in one process as two distinct
module objects** with two distinct global namespaces. `create_app()` loads the route under the
top-level path; the test module imports it under the `services.` path. A test that patches the
wrong instance silently asserts nothing. The tests resolve the instance from the **live app's
own route**, and assert the resolved module's `__dict__` is the function's globals.

The same hazard applies to `sys.platform`: it is the shared stdlib module, and mutating it
corrupts unrelated runtime behaviour (asyncio / anyio). The module therefore reads
`HOST_PLATFORM`, which tests patch instead.

---

## 5. Documentation corrections

| File | Change |
|---|---|
| `docs/08_security/security-strategy.md` | A-F11 §A-F11 properties 2, 3 and 4 corrected to state the per-platform reality. Property 4 now states the **per-process `RLIMIT_AS` limit**, **explicitly denies an aggregate process-tree memory budget**, and states that Windows PDF parsing is **unsupported** pending B2. Each superseded wording is preserved and labelled. |
| `docs/16_audit/BBF-FU-21-windows-scope.md` | §1.1 table row 3 and §4 corrected: `win32job` is **not** imported and `pywin32` is **not** a dependency. The original claim is quoted in place, labelled superseded. A dated `§N. Correction` section records the audit trail. The brief's **§1.3 verdict is unaffected** — Job Objects still do not provide filesystem isolation. |
| `docs/16_audit/BBF-FU-20-impl-windows.md` | §1 corrected to agree with §5; the self-contradiction is labelled and resolved, both statements preserved. |
| `docs/16_audit/OPEN-FOLLOWUPS.md` | FU-22 reopened as **PARTIALLY RESOLVED**; the 2026-10-16 RESOLVED claim preserved verbatim as history; a dated correction records the three reasons; a new `## Resolved`-section record states the contract and the B2 obligations. **FU-20's status and entries are unchanged.** |

---

## 6. Outstanding — B2 (separately approved; **not** implemented here)

- Real Windows Job Object enforcement (`JOB_OBJECT_LIMIT_PROCESS_MEMORY`), with the job
  lifecycle, descendant inclusion, kill-on-close semantics and limit-violation reporting
  defined.
- An **explicitly declared dependency** (`pywin32`) if that mechanism is used.
- A **Windows CI job** capable of exercising process-tree memory enforcement (the repository
  has none: every one of the 16 CI jobs is `ubuntu-latest`).
- **Executable Windows enforcement tests**, including a negative control that distinguishes a
  real enforced limit from a constant.

**B1 explicitly does not add, imply, or claim:** `win32job` or any Job Object mechanism;
`pywin32` or any new dependency; a Windows CI matrix; Windows resource-limit enforcement;
Windows PDF parsing that runs without enforceable resource control; or the separate uncapped
engine-subprocess path (which requires its own finding and threat model).

**Until B2 lands, Windows PDF parsing is unsupported by design.** FU-22 is therefore **not**
fully resolved.

---

## 7. Scope discipline

- The 2 GB constant is unchanged.
- The Linux mechanism is unchanged.
- No dependency was added; `pyproject.toml` and `uv.lock` are untouched.
- No CI workflow file was modified.
- The six pre-existing stale ledger pointers were **not** repaired.
- The `chess_coach.gold` package-declaration question was **not** touched.
- FU-20 was **not** modified.
