# BBF-doc-drift-flip-7 — flip FU-21 to RESOLVED in OPEN-FOLLOWUPS.md

**Sprint intent:** Close the stale `Status (clarified
2026-10-18, doc-drift flip-6): PARTIALLY RESOLVED` ledger
entry in `docs/16_audit/OPEN-FOLLOWUPS.md`:

- **FU-21** (line 1714): the A-F11 property 3 (read-only
  filesystem) implementation gap. **RESOLVED
  2026-10-19** on both the Linux full-enforcement surface
  AND the Windows deployment-config surface:
  - Linux: BBF-FU-21-bind-mount (squash `d3fbb35c`, PR #169)
    completed the bind-mount step inside
    `set_fs_isolation_preexec(tmpdir)`.
  - Windows: BBF-FU-21-windows-scope (squash `db0e4121`, PR #168)
    closed the Windows path as a deployment-config concern
    per `BBF-FU-20-21-22-A-F11-spikes.md` Section B.

This is the **7th doc-drift flip**. Unlike flips 1-6
(which were bookkeeping for prior impls that had landed),
flip-7 is the **closure** of the FU-21 entry: both the
Linux impl AND the Windows scope decision have shipped
on main, so the entry can flip from PARTIALLY RESOLVED
to RESOLVED.

**Status:** Doc-only BBF. 1 file modified.

## §1. The flip pattern (matches BBF-doc-drift-flip-6)

Per the v0.2.0 clarification pattern (verified PR #93),
the flip **prepends** a new `**Status (clarified
2026-10-19, doc-drift flip-7):**` block before the prior
flip-6 `**Status (clarified 2026-10-18, doc-drift flip-6):**`
block of the FU-21 entry. Both prior blocks (the original
`**Status:** OPEN` and the flip-6 PARTIALLY RESOLVED) are
preserved as historical context.

The new block:
- States **RESOLVED 2026-10-19** on both surfaces.
- Cites the actual squash SHAs (`d3fbb35c` for Linux,
  `db0e4121` for Windows) — verified via
  `git merge-base --is-ancestor <sha> origin/main` (each
  exit 0).
- Names the test surface that verifies the bind-mount
  step (`test_set_fs_isolation_preexec_performs_mount_on_linux_with_capability`).
- Names the deployment-config-artifact separation
  (AppLocker / WDAC are system-wide; policy XML lives in
  a separate repo, not this one).

## §2. The verify-first pre-flight

**Per the §1.3 + §13.1 STOP gate discipline, the session
held the gate before any state-mutating action.** The
prior session's BBF-doc-drift-flip-7 directive surfaced a
critical finding: PR #169 (`ee1aac3d`) was NOT yet on
main, and flipping before the impl commit lands would
have been the same ledger bug pattern as flip-6 (where
BBF-FU-21-impl shipped without its own Status block).

The fix was a two-step sequence per the user's `go a`:

| Step | BBF | Outcome |
|---|---|---|
| 1 | BBF-FU-21-bind-mount (PR #169, `d3fbb35c`) | ✓ squash-merged first — verified 15/15 green on `ee1aac3d` amend SHA |
| 2 | **BBF-doc-drift-flip-7 (PR #170, this BBF)** | in progress — flips the ledger now that step 1 is on main |

This two-step pattern matches the prior session's
`go a` sequence (flip-6 + FU-21-windows-scope), which
also enforced step-by-step sequencing between bind-mount
impl and ledger-update BBFs.

## §3. The verification (live, this session)

```
# All 4 SHAs cited in the flip are reachable from main:
$ git merge-base --is-ancestor d3fbb35c origin/main  # exit 0
$ git merge-base --is-ancestor db0e4121 origin/main  # exit 0
$ git merge-base --is-ancestor 8877ab81 origin/main  # exit 0 (the flip-6 PARTIALLY-RESOLVED)
$ git merge-base --is-ancestor 1487ff76 origin/main  # exit 0 (the flip-6 squash)

# The flip adds 38 lines (status block) + 5 lines
# (cross-references) to OPEN-FOLLOWUPS.md. No code
# changes. The brief is +158 lines.

# Byte-level + CRLF scan on OPEN-FOLLOWUPS.md:
#   corruption: none
#   crlf: False (LF preserved per repo convention)
```

## §4. The §1.3 catches

1. **No code changes.** The diff is `*.md` only.
   `set_fs_isolation_preexec()` is unchanged from PR #169;
   the flip reflects the existing implementation.

2. **No fabricated SHAs** (cf. flip-4's `bd5a8267`
   fabrication): all 4 SHAs in the flip are verified by
   `git merge-base --is-ancestor` (each exit 0). The
   cites are honest.

3. **Both clarification blocks preserved.** The original
   `**Status:** OPEN` (line 1701) and the flip-6
   `**Status (clarified 2026-10-18, doc-drift flip-6):**
   PARTIALLY RESOLVED` (line 1714) are preserved as
   historical context above the new
   `**Status (clarified 2026-10-19, doc-drift flip-7):**
   RESOLVED` block. The "LIVE status" language makes the
   historical-vs-current distinction explicit.

4. **Cross-references section updated.** Added 5 new
   lines pointing at: `BBF-FU-21-bind-mount.md` (squash
   `d3fbb35c`), `BBF-FU-21-windows-scope.md` (squash
   `db0e4121`), `BBF-doc-drift-flip-6.md` (squash
   `1487ff76`), and `BBF-doc-drift-flip-7.md` (this brief).

## §5. Honest disclosures

1. **The Linux enforcement is environment-conditional.**
   The bind-mount step runs ONLY when the test/prod
   environment has `CAP_SYS_ADMIN` or
   `kernel.unprivileged_userns_clone`. The negative-
   invariant test in
   `test_set_fs_isolation_preexec_performs_mount_on_linux_with_capability`
   is skip-gated on environments without the capability.
   On capability-absent hosts the subprocess inherits
   the parent's filesystem unchanged (the BBF-FU-21-impl
   "fallback no-op" behavior is preserved). Production
   hosts (Tauri desktop apps on Linux with CAP_SYS_ADMIN
   by default) get the full bind-mount enforcement.

2. **The Windows path is closed as a deployment-config
   concern, not a code concern.** The production-correct
   answer for Windows filesystem enforcement is
   AppLocker / WDAC system-wide policy, configured by an
   administrator at deployment time. That policy lives
   in a separate deployment-config repo (not this one).
   On unconfigured hosts, the subprocess's filesystem
   is open as today. The closure shape: "the Python
   enforcement is complete; the OS-level enforcement is a
   separate operational deliverable."

3. **No 8th doc-drift flip is queued.** Per the
   `BBF-doc-drift-flip-7 §3.1` and the §5 honest
   disclosure #2 of flip-6, this is the closure of the
   FU-21 ledger entry. The remaining OPEN FUs (FU-9,
   FU-11β, FU-23, FU-27) are genuinely unimplemented work,
   not bookkeeping — they each need their own
   implementation or a separate flip.

4. **The well is now dry.** Per the prior session's
   "well is drying up" observation (PR #97) and the
   explicit discipline in flip-6 §5 #1: doc-drift flips
   past round N carry diminishing marginal value. This
   7th flip is justified by the closure semantic (FU-21
   ledger now correctly reflects the actual implementation
   state on main). It is NOT justified by being a "fresh
   finding" — there are no fresh findings left to ship as
   flips. The next productive direction is real
   implementation work.

## §6. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-21 entry
  (line 1714, +43/-0 status block + 5 cross-reference
  lines).
- `docs/16_audit/BBF-FU-21-impl.md` (brief, squash
  `8877ab81`).
- `docs/16_audit/BBF-FU-21-bind-mount.md` (brief,
  squash `d3fbb35c`).
- `docs/16_audit/BBF-FU-21-windows-scope.md` (brief,
  squash `db0e4121`).
- `docs/16_audit/BBF-doc-drift-flip-6.md` (prior
  ledger flip, squash `1487ff76`).
- `services/chess_coach/pdf_ocr/subprocess_runner.py:281`
  (the function whose signature was refactored in
  `d3fbb35c` to accept `tmpdir: Path | None = None`).
- `tests/unit/test_subprocess_runner.py` (the unit
  test file extended in `d3fbb35c` with the
  bind-mount assertion test).
- `tests/unit/test_pdf_ingest_security.py`
  (skip reason updated in `d3fbb35c`).
- PR #169 (BBF-FU-21-bind-mount, squash `d3fbb35c`).
- PR #168 (BBF-FU-21-windows-scope, squash `db0e4121`).
- PR #167 (BBF-doc-drift-flip-6, squash `1487ff76`).
- PR #166 (BBF-FU-21-impl, squash `8877ab81`).

## §7. The §13.1 STOP gate (between BBFs in sequence)

This flip is BBF #2 of the user's `go a` (with the
implicit step "first merge BBF-FU-21-bind-mount, then
flip"). The bind-mount merge (BBF #1) is verified on
main. This flip is the second-and-final BBF; per the
skill, no further BBFs are auto-advanced after merge.
Standing by for `go BBF-doc-drift-flip-7` to squash-merge.
