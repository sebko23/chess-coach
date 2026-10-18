# BBF-doc-drift-flip-4 — flip FU-20 to PARTIALLY RESOLVED in OPEN-FOLLOWUPS.md

**Sprint intent:** Close the stale `OPEN` ledger entry
in `docs/16_audit/OPEN-FOLLOWUPS.md`:

- **FU-20** (line 1620): the A-F11 property 2 (network
  isolation) implementation gap. Partially closed by
  PR #163 and PR #164 (BBF-FU-20-impl + BBF-FU-20-impl-windows).
  The Linux path is complete (`unshare(CLONE_NEWNET)`);
  the Windows path is best-effort (env-var stripping).

**Status:** Doc-only BBF. 1 file modified.

## §1. The flip pattern (matches BBF-doc-drift-flip-2/3)

Per the v0.7.128 (sigma) meta-footgun, the flip
prepends a `**Status:** **RESOLVED ...**` line at the
top of each existing FU section, preserving the
original narrative. No entries are moved to the
`## Resolved` section (that's a different convention
used by older entries; the current convention is the
prepended Status line).

## §2. The flip

### FU-20 — A-F11 property 2 (network isolation) has no implementation or test

**Status:** **PARTIALLY RESOLVED 2026-10-18 via
squash-merge of PR #163 and PR #164** (feature commits
`190a0c27` (under merge `4c11159c`) and `913652c3`
(under merge `fa0bfd73`), BBF-FU-20-impl +
BBF-FU-20-impl-windows).

The Linux path is complete: `set_network_isolation_preexec()`
in `services/chess_coach/pdf_ocr/subprocess_runner.py`
calls `os.setsid()` to create a new session, then
`unshare(CLONE_NEWNET)` via ctypes to enter a fresh
network namespace (no loopback, no localhost, no DNS,
no outbound TCP/UDP).

The Windows path is best-effort: strips proxy env vars
(`http_proxy`, `https_proxy`, `all_proxy`, `no_proxy`
and their uppercase variants) since the `pywin32`
module does not expose `SetInformationJobObject` for
`JobObjectNetRateControlInformation`.

3 new tests added to `tests/unit/test_subprocess_runner.py`
(7 passed, 2 skipped on Windows). CI: 15/15 green on
main (`fa0bfd73`).

**Out of scope (follow-up BBFs):**
1. Full Windows network isolation via custom C
   extension or AppContainer (requires significant
   new code).
2. Verification that `unshare(CLONE_NEWNET)` actually
   creates a new network namespace (the existing test
   only verifies `os.setsid()` runs).
3. The `JOB_OBJECT_LIMIT_PROCESS_MEMORY` (memory cap
   on Windows, separate from network isolation) — was
   deferred by FU-22-impl.

## §3. The §1.3 catches (exemplary discipline)

1. **CRLF footgun in OPEN-FOLLOWUPS.md** (pre-commit) —
   The file was 3046 CRLF lines in my local working
   copy. The convert-to-LF step is automatic in this
   session's workflow; verified clean diff (+4 lines,
   no line-ending churn).

## §4. Honest disclosures

1. **FU-20 is PARTIALLY RESOLVED.** The Linux path is
   complete (full network namespace isolation). The
   Windows path is best-effort (env-var stripping only).
   The Status line reflects this honestly: "PARTIALLY
   RESOLVED" with the remaining work documented in the
   "Out of scope" paragraph.

2. **No code changes; no test changes; no CI impact.**
   This BBF is doc-only, matching the prior
   BBF-doc-drift-flip pattern (PR #142, #146, #162).

3. **Per the v0.7.114 nit-fold discipline, doc-only BBFs
   that don't touch CI are below the re-review threshold.**
   The leaf review is waived for this BBF.

4. **The 7 still-open FUs** (FU-5, FU-6, FU-9, FU-11,
   FU-21, FU-23, FU-27) are NOT in scope for this BBF.
   Each has its own resolution work; this BBF is
   bookkeeping only for FU-20.

## §5. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-20 entry (line 1620, +4 lines Status block).
- `docs/16_audit/BBF-FU-20-impl.md` (squash feature commit `190a0c27`, PR #163 merge `4c11159c`).
- `docs/16_audit/BBF-FU-20-impl-windows.md` (squash feature commit `913652c3`, PR #164 merge `fa0bfd73`).
- `services/chess_coach/pdf_ocr/subprocess_runner.py` (the module modified by the two BBFs).
- `tests/unit/test_subprocess_runner.py` (the test file extended by the two BBFs).
- PR #142 (`BBF-doc-drift-flip`), PR #146 (`BBF-doc-drift-flip-2`), PR #162 (`BBF-doc-drift-flip-3`) — the prior doc-drift-flip pattern.
