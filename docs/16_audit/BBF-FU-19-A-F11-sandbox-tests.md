# BBF-FU-19-A-F11-sandbox-tests — add 4 A-F11 sandbox-isolation tests to `tests/unit/test_pdf_ingest_security.py`

**Sprint intent:** Add 4 new tests to
`tests/unit/test_pdf_ingest_security.py` that exercise
the 4 unenforced A-F11 sandbox-isolation contract
properties (subprocess isolation, no network access,
read-only filesystem, 2 GB memory cap). The existing
9 tests in the file cover the route-layer pre-validation
(file-size cap, magic bytes) and the 5-min timeout. The
4 new tests close the **sand box** side of the A-F11
contract.

**Identified:** 2026-10-16, during the `go FU-19` directive.
Per `docs/08_security/security-strategy.md` §A-F11
"Properties enforced today", the PDF parser contract has
5 properties; only property 5 (5-min timeout) is currently
tested. Properties 1-4 (subprocess isolation, no network,
read-only fs, 2 GB cap) are **partially or not at all
enforced** and have no tests.

**The 4 A-F11 properties + their current state:**

| # | Property | Enforced today? | Tested today? |
|---|---|---|---|
| 1 | Subprocess isolation (Popen, separate OS process) | Partial — `pdf2image.convert_from_bytes` uses `Popen` internally | **No** (regression risk: someone replaces pdf2image with PyMuPDF in-process) |
| 2 | No network access | **No** — subprocess inherits parent's network | **No** (gap) |
| 3 | Read-only filesystem (except per-book artifact dir) | **No** — pdf2image writes via `tempfile.mkstemp()` | **No** (gap) |
| 4 | 2 GB memory cap | **No** — no `RLIMIT_AS` or Job Object | **No** (gap) |
| 5 | 5-min timeout | Yes (in pdf_ingest.py) | **Yes** (in `test_route_uses_asyncio_wait_for_wrapper` etc.) |

**The 4 new tests:**

| # | Test name | What it asserts | Pass/fail expectation today |
|---|---|---|---|
| 1 | `test_pdf_parsing_runs_in_separate_subprocess` | `pdf2image.convert_from_bytes` is invoked with `timeout` and that the underlying call goes through `subprocess.Popen` (not an in-process library) | **PASS** — pdf2image uses Popen internally |
| 2 | `test_subprocess_cannot_initiate_outbound_network` | The PDF-parsing subprocess has no network access | **`skip`** — gap; will start exercising when FU-22 lands |
| 3 | `test_subprocess_filesystem_writes_restricted_to_artifact_dir` | The PDF-parsing subprocess can only write to the per-book artifact dir | **`skip`** — gap; will start exercising when FU-21 lands |
| 4 | `test_subprocess_respects_2gb_memory_cap` | A PDF that would balloon RSS > 2 GB is killed by the sandbox | **`skip`** — gap; will start exercising when FU-20 lands |

Test 1 is a real, meaningful test (catches the regression
risk of replacing pdf2image with in-process PyMuPDF). Tests
2-4 use `pytest.skip` markers with explicit reasons
pointing at the future implementation BBF (FU-22, FU-21,
FU-20 respectively). They will be turned into real
assertions by the future implementation BBF.

**Why this is a §1.3-honest test design:**

- The contract is documented in
  `docs/08_security/security-strategy.md` §A-F11.
- The implementation status is documented in the same
  section ("Properties enforced today (and the tests
  that hold them)").
- The current test file already tests property 5 (timeout)
  and the route-layer pre-validation.
- The 4 new tests close the test-coverage gap: each
  test explicitly references the A-F11 property number,
  the implementation status per the strategy doc, and
  the future implementation BBF that will close the gap.
- Tests 2-4 use `pytest.skip(reason="...")` so the CI
  never fails on them until the corresponding
  implementation lands. This is the standard pattern
  for "test the contract that isn't yet enforced."
- Test 1 is a real, non-skip assertion because property
  1 IS partially enforced today (pdf2image uses Popen).

**The 2 test mechanisms used:**

1. **Mocking** `pdf2image.convert_from_bytes` (or
   `subprocess.Popen` at the right level) to assert the
   call shape for test 1.
2. **`pytest.skip`** for tests 2-4 with explicit reasons
   pointing at the future implementation BBF.

**Work product:**

This BBF produces 2 file changes:

1. `tests/unit/test_pdf_ingest_security.py` (modified,
   +~120 lines) — 4 new test functions added at the end
   of the file, in a new section "E. A-F11 sandbox
   isolation properties (FU-19, 2026-10-16)".
2. `docs/16_audit/BBF-FU-19-A-F11-sandbox-tests.md` (NEW,
   ~150 lines) — this brief.

**Out of scope (NOT in this BBF):**

- **The actual implementation of properties 2, 3, 4**
  (network isolation, read-only fs, 2 GB cap). These are
  their own BBFs (FU-22, FU-21, FU-20). This BBF
  documents the contract; the implementation BBFs
  implement the contract.
- **Property 5 (timeout) tests** — already covered by
  the existing 9 tests in this file.
- **Refactoring or improving the existing 9 tests** —
  out of scope; this BBF is additive only.

**Honest disclosures:**

- **Test 1 (subprocess isolation) is a real test** that
  asserts the current code path goes through `Popen`. It
  is **not** a skip test. The test catches a regression where
  someone replaces `pdf2image.convert_from_bytes` with
  an in-process library (e.g. PyMuPDF) that doesn't use
  `Popen`. The historical A-F11 description originally
  anticipated PyMuPDF; the current implementation uses
  pdf2image/Poppler. The test holds that choice.
- **Tests 2-4 use `pytest.skip`**, with explicit `reason=`
  strings pointing at the future implementation BBF
  (FU-22, FU-21, FU-20 respectively). `skip` makes the
  test an explicit "not yet testing this" marker in
  the CI report. The CI itself does not fail; the test
  is a tripwire for future implementation work. The
  implementation BBFs (FU-22, FU-21, FU-20) remove the
  `@pytest.mark.skip` marker and add a real assertion
  that exercises the property.
- **The existing `test_route_uses_asyncio_wait_for_wrapper`**
  (property 5) is **not** a skip test; it's a real test. This
  BBF does not touch it.
- **`pytest.skip` requires no env-var or feature-flag**
  mechanism; the tests are always skipped until the
  corresponding implementation lands, regardless of
  environment.

**Hermes verification (re-derive, post-merge):**

- `pytest tests/unit/test_pdf_ingest_security.py` shows
  9 passed (existing 9) + 1 passed (new test 1) + 4 skipped
  (1 preexisting + 3 new) = 13 total, 9 passed, 1 skipped (preexisting),
  3 skipped (new gap-documentation). The 3 newly-skipped
  tests reference the future implementation BBFs
  (FU-22, FU-21, FU-20) in their `reason=` strings
  for traceability.
- `git show main:tests/unit/test_pdf_ingest_security.py
  | tail -200` shows the 4 new tests at the end of the
  file in section E.

**Final report format:** the squash-merge commit body
documents the 4 new tests + the 2-file scope + the
skip/explicit-pass split. The commit body uses
inline-backtick-wrapped `path:N` references where
appropriate and paraphrases where not, per the v0.7.128
(σ) discipline.
