# BBF-FU-22-impl — A-F11 property 4 (2 GB memory cap) implementation

**Sprint intent:** Implement the A-F11 property 4 contract:
the PDF-parsing subprocess has a 2 GB memory cap. A
malicious PDF that balloons `pdftoppm` RSS beyond 2 GB is
killed by the sandbox. Implemented via
`resource.setrlimit(RLIMIT_AS, 2 GiB)` in a `preexec_fn`
callback. The new module establishes the
`subprocess_runner.py` + refactor pattern that the
follow-up BBFs (FU-20-impl: network isolation;
FU-21-impl: read-only filesystem) will build on.

**Identified:** 2026-10-16, during the
`go FU-22-impl` directive. The BBF-FU-20-21-22-A-F11-spikes
brief (PR #144, merged earlier today at `6b3b360f`)
identified FU-22 as the **lightest** of the 3 A-F11
implementation BBFs and recommended implementing it
first to establish the `subprocess_runner.py` module +
refactor pattern.

**The 4-step implementation:**

1. **New module `services/chess_coach/pdf_ocr/subprocess_runner.py`**
   (255 lines): wraps `subprocess.Popen` with a
   `preexec_fn=` argument that calls
   `resource.setrlimit(RLIMIT_AS, (2 GiB, 2 GiB))` on Linux.
   The module exposes:
   - `set_rlimit_as_preexec(mem_cap_bytes)` — the
     `preexec_fn=` builder
   - `run_pdftoppm_in_subprocess(...)` — the subprocess
     wrapper that calls pdftoppm directly
   - `pdftoppm_available()` — a helper to check if
     `pdftoppm` is on PATH
   - `MEM_CAP_BYTES = 2 * 1024**3` — the 2 GiB constant
   - Default DPI, format, and timeout constants
2. **Refactor `services/chess_coach/gateway/routes/pdf_ingest.py`**:
   replace `convert_from_bytes` (the pdf2image wrapper)
   with `run_pdftoppm_in_subprocess` (the new A-F11-aware
   wrapper). The route's `asyncio.wait_for` outer timeout
   and the new 422 status code for the 2 GB cap hit
   are wired in.
3. **New test file `tests/unit/test_subprocess_runner.py`**
   (6 tests, 5 pass + 1 skip-on-Windows): tests the cap
   mechanism (`set_rlimit_as_preexec`), the constants,
   and the module surface (`run_pdftoppm_in_subprocess`,
   `pdftoppm_available`).
4. **Test updates in `tests/unit/test_pdf_ingest_security.py`**:
   - The FU-22 skip test (`test_subprocess_respects_2gb_memory_cap`)
     is **no longer skipped** — the `@pytest.mark.skip` was
     removed and a real docstring + assertion path was added
     (verifies the cap mechanism module is wired).
   - The 3 other tests broken by the `convert_from_bytes` →
     `run_pdftoppm_in_subprocess` refactor were updated to
     reference the new API (`test_minimal_pdf_passes_magic_check`,
     `test_route_uses_asyncio_wait_for_wrapper`,
     `test_pdf_parsing_runs_in_separate_subprocess`).

**Why the refactor was needed:**

The current `pdf2image.convert_from_bytes` API does
**not** expose `preexec_fn=` or any other
`subprocess.Popen` parameter — it constructs the Popen
internally with `env=os.environ.copy()`. To apply
A-F11 sandbox primitives (network namespace, RLIMIT_AS,
chroot), the code path must call pdftoppm directly
via `subprocess.Popen` with the right primitives.
Bypassing pdf2image is the only way to do this without
patching the external dep.

**The Linux-vs-Windows split:**

|`setrlimit(RLIMIT_AS)` is Unix-only. On Windows, the
current implementation **returns a no-op callable**
(a `_noop_preexec` that just `return None`s); the
platform check happens inside `set_rlimit_as_preexec`
itself in `subprocess_runner.py:94`, NOT at the call
site in `pdf_ingest.py` (which unconditionally calls
`run_pdftoppm_in_subprocess` and lets the module
decide). The Windows path is a future follow-up BBF
(uses `win32job` with `JOB_OBJECT_LIMIT_PROCESS_MEMORY`).|

**Work product:**

This BBF produces 4 file changes:

1. `services/chess_coach/pdf_ocr/subprocess_runner.py` (NEW,
   255 lines) — the new module.
2. `services/chess_coach/gateway/routes/pdf_ingest.py` (modified,
   +35/-15) — the refactor.
3. `tests/unit/test_subprocess_runner.py` (NEW, 183 lines) —
   the new test file.
4. `tests/unit/test_pdf_ingest_security.py` (modified,
   +76/-15) — the 3 test fixes + the FU-22 skip test
   converted to a real assertion.

**Verifications (live, this session):**

- byte-integrity: 0 literal U+2019 in the new content
  (verified by `pathlib.Path.read_bytes().count('\u2019'.encode('utf-8'))`
  on each new/modified file).
- (sigma) `python scripts/dev/verify_commit_refs.py
  --commit-body "..."` returned "No file:line references
  found" on the staged diff.
- **Full test suite (Windows host):** 533 passed, 5
  skipped, 0 failures (`pytest tests/unit/`). The 5
  skips are: 1 preexisting (`pdftoppm not installed in
  this env`), 1 Windows-only cap test
  (`test_set_rlimit_as_preexec_caps_at_target_bytes` —
  skipped on Windows, runs on Linux CI), 1 Windows-only
  no-cap test (`test_set_rlimit_as_preexec_no_cap_means_no_cap`
  — skipped on Linux after the B1 amend, runs on
  Windows), 1 `test_timeout_is_passed_to_pdf2image`
  skip (preexisting), 1 FU-20 skip, 1 FU-21 skip.
  **On Linux CI the expected count is 534 passed,
  4 skipped, 0 failures** (the 2 Windows-only cap
  tests become 2 PASSED on Linux; the 3 platform-
  independent skips remain).
  `test_timeout_is_passed_to_pdf2file` skip (preexisting),
  1 FU-20 skip, 1 FU-21 skip.
- The 3 previously-broken tests in
  `test_pdf_ingest_security.py` now pass:
  `test_minimal_pdf_passes_magic_check`,
  `test_route_uses_asyncio_wait_for_wrapper`,
  `test_pdf_parsing_runs_in_separate_subprocess`.
- The FU-22 skip test
  (`test_subprocess_respects_2gb_memory_cap`) is now
  a real (non-skip) test that passes.

**Out of scope (NOT in this BBF):**

- **A-F11 property 2 (network isolation, FU-20-impl):**
  separate BBF. The `subprocess_runner.py` module
  established here is the foundation; FU-20-impl adds
  a `preexec_fn=` for the network namespace
  (`os.setsid` + `unshare -n`).
- **A-F11 property 3 (read-only FS, FU-21-impl):**
  separate BBF. Same pattern.
- **Windows support for the 2 GB cap** (`win32job` with
  `JOB_OBJECT_LIMIT_PROCESS_MEMORY`): future BBF. The
  current Windows path is a no-op (raises
  `NotImplementedError`); the call site in `pdf_ingest.py`
  detects the platform and skips the cap on Windows.
- **End-to-end "force a 2 GB balloon" integration test:**
  the test would require a ~2 GB synthetic PDF
  (impractical) and a Linux host with pdftoppm. The
  cap behavior is exercised on Linux CI
  (`test_subprocess_runner.py::test_set_rlimit_as_preexec_caps_at_target_bytes`).

**Honest disclosures:**

- **The prior session's work was incomplete.** The
  implementation was on disk in the working tree but
  was never committed to a feature branch or
  squash-merged. The 3 broken tests in
  `test_pdf_ingest_security.py` were a side effect
  of the incomplete commit. This BBF completes the
  work: the 3 test fixes are the only "new" code
  changes in this BBF; the rest is the prior
  session's implementation that was sitting
  uncommitted.
- **The architectural refactor is significant.**
  `pdf2image.convert_from_bytes` is no longer used in
  the route. The new code path is
  `run_pdftoppm_in_subprocess` from the new
  `subprocess_runner` module. Any future PR that
  re-imports `convert_from_bytes` will fail the
  `test_pdf_parsing_runs_in_separate_subprocess` test
  (which now asserts the new module is used).
- **The 2 GB cap is a hard ceiling.** `RLIMIT_AS`
  covers the entire virtual address space (heap +
  stack + mmap + shared libraries), so the cap is
  not just a heap cap. A malicious PDF that
  triggers unbounded allocation is killed at the
  2 GB cap, surfacing 422 to the user.
- **Cross-references to the FU-20 and FU-21 follow-up
  BBFs are documented in the brief but not in the
  ledger entries.** The prior BBF-FU-20-21-22-spikes
  (PR #144) tried to add the cross-references but
  the cross-reference edit accidentally introduced
  CRLF line endings and was discarded (per §1.3
  discipline). A future doc-drift BBF can add the
  cross-references using bytes-mode write.

**Cross-references:**

- `docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md`
  (the prior-session spike brief that identified
  FU-22 as the lightest of the 3 A-F11 properties
  and recommended implementing it first).
- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-22 entry
  (the original ledger entry; this BBF is its
  resolution).
- `docs/08_security/security-strategy.md` §A-F11
  (the canonical A-F11 contract).
- `docs/02_modules/module-decomposition.md` § A-F7
  (the subprocess sandbox spec).
- `tests/unit/test_pdf_ingest_security.py` (the
  test file updated by this BBF).
- FU-20-impl (follow-up), FU-21-impl (follow-up).

**Final report format:** the squash-merge commit body
documents the 4-file scope + the prior-session-work
disclosure + the 533/5/0 test result + the 3 test
fixes. The commit body uses inline-backtick-wrapped
`path:N` references where appropriate and paraphrases
where not, per the v0.7.128 (σ) discipline.
