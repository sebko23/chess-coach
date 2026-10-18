# BBF-doc-drift-flip-6 — flip FU-21 to PARTIALLY RESOLVED in OPEN-FOLLOWUPS.md

**Sprint intent:** Close the stale `Status: OPEN` ledger entry
in `docs/16_audit/OPEN-FOLLOWUPS.md`:

- **FU-21** (line 1714): the A-F11 property 3 (read-only
  filesystem) implementation gap. Partially closed by
  PR #166 (squash-commit `8877ab81`, BBF-FU-21-impl,
  brief at `docs/16_audit/BBF-FU-21-impl.md`). The
  Linux path is partial: `set_fs_isolation_preexec()`
  attempts `unshare(CLONE_NEWUSER|CLONE_NEWNS)` via
  ctypes with a no-op fallback on capability failure.
  The full read-only filesystem enforcement requires
  threading the per-book artifact dir through the
  preexec_fn closure (a follow-up BBF). The Windows path
  is a no-op (AppLocker/WDAC requires system-wide admin
  policy; the follow-up BBF-FU-21-windows-scope scope
  brief is the next sequence).

**Status:** Doc-only BBF. 1 file modified.

## §1. The flip pattern (matches BBF-doc-drift-flip-4)

Per the v0.7.128 (sigma) meta-footgun, the flip
prepends a `**Status (clarified YYYY-MM-DD):** **PARTIALLY
RESOLVED**` block before the existing `**Status:** OPEN`
line of the FU-21 entry, preserving the original Status
line as historical context. The v0.2.0 clarification
pattern (verified PR #93) is the right shape here
because the original Status line was historically
accurate (true at write time on 2026-08-13, during the
FU-19 / A-F11 BBF session) but became stale relative to
current `main` once PR #166 landed.

The clarification block cites the squash-merge SHA
(`8877ab81`) and the post-merge state of the FU-21
preexec_fn at
`services/chess_coach/pdf_ocr/subprocess_runner.py:281`.

## §2. The verify-first pre-flight that surfaced this BBF

This BBF exists because of an honest verify-first
finding from the BBF-FU-21-windows-scope pre-flight
session. The original BBF-FU-21-impl (PR #166) shipped
on 2026-10-18 with diffstat covering only the brief
+ code + tests; the `OPEN-FOLLOWUPS.md` Status block
update for FU-21 was NOT in the PR branch and therefore
NOT in the squash-merge. The ledger entry remained
`Status: OPEN` even though the implementation IS on
main.

This is the (T) memory-entry corollary: ledger-flip
BBFs that update `OPEN-FOLLOWUPS.md` lines need to
verify the line-update lands, not just the brief-add.
Verified via `git show 8877ab81 --stat` (the squash
stat did NOT include `OPEN-FOLLOWUPS.md`) +
`git diff 8877ab81 ec585896 -- docs/16_audit/OPEN-FOLLOWUPS.md`
(empty result, confirming the PR branch never
modified the file).

## §3. The verification (live, this session)

The clarification block content is grounded per
direct evidence:

- `services/chess_coach/pdf_ocr/subprocess_runner.py:281`:
  the function `set_fs_isolation_preexec()` exists.
  `CLONE_NEWUSER = 0x10000000` and `CLONE_NEWNS = 0x00020000`
  constants exist at lines 378-379 (per `grep -n`).
- `docs/16_audit/BBF-FU-21-impl.md`: the brief is
  tracked on main (verified via `git ls-tree origin/main
  docs/16_audit/BBF-FU-21-impl.md`).
- `8877ab81`: the squash-merge SHA (verified via
  `git log -1 --format=%h`).
- §4 honest-disclosure #2 of the brief explicitly states
  the bind-mount thread-through-tmpdir step is the
  follow-up BBF.

The clarification block cites all four anchors
correctly. The cross-references section at the end of
the FU-21 entry adds two new lines pointing at
`BBF-FU-21-impl.md` (brief) and `BBF-FU-20-21-22-A-F11-spikes.md`
Section B (upstream scoping).

## §4. The §1.3 catches

1. **SHA-citation discipline (memory T)**: the
   clarification block cites `8877ab81` directly. Verified
   via `git rev-parse 8877ab81` (the SHA exists) and
   `git merge-base --is-ancestor 8877ab81 origin/main`
   (exit 0, confirmed reachable from main). For the
   `BBF-FU-21-impl.md` brief reference, the SHA is the
   squash-merge SHA (single-commit squash-style merge
   per PR #166, so the merge SHA IS the feature SHA).
   No fabricated SHAs (cf. flip-4's `bd5a8267` bug
   where `bd5a8267` was made up; this time the SHA is
   real).

2. **File-line anchors**: `services/chess_coach/pdf_ocr/subprocess_runner.py:281`
   for `set_fs_isolation_preexec`. Verified via
   `git show origin/main:services/chess_coach/pdf_ocr/subprocess_runner.py`
   lines 281-282.

3. **byte-level hygiene**: the modified `OPEN-FOLLOWUPS.md`
   is UTF-8 clean (no `\u[0-9a-fA-F]{4}` literal escape
   sequences) and CR/LF clean (preserves the repo's
   LF-only convention per `git show origin/main:docs/16_audit/OPEN-FOLLOWUPS.md`).

## §5. Honest disclosures

1. **This is the 6th doc-drift flip** (PR #90, #91,
   #93, #96, #97, #162, and now this). The cycle is
   past its productive per-finding yield. Per the
   session reflection on 2026-10-13 (PR #97), the
   "well is drying up" discipline applies: doc-only
   flips past round N carry diminishing marginal
   value. This flip is justified not by being a fresh
   finding but by a *real* ledger-state gap that
   surfaces *exactly* the (T) memory corollory that
   "ledger-flip BBFs need to verify the line-update
   lands." Without this flip, the next session
   picking up FU-21 would re-verify, discover the same
   gap, and ship another drift patch — net negative
   session time. With this flip, the next session's
   BRIEF-vs-code divergence check can confirm the
   clarification block is on main.

2. **The flip is clarification-only.** The implementation
   itself is already on main (per PR #166 / commit
   `8877ab81`). The flip does not introduce new
   semantics; it documents the existing semantics in
   the ledger.

3. **The next BBF in the sequence** (per the user's
   directive `go FU-21-impl-windows`) is
   `BBF-FU-21-windows-scope`, the doc-only
   investigation-first brief for the AppLocker/WDAC
   deferral. It is NOT this BBF. This BBF is the
   bookkeeping flip; the next BBF is the Windows
   scope decision. Per the skill: "do not bundle
   multiple BBFs into a single ship cycle even when
   the user lists them in one prompt." Each BBF
   gets its own branch + PR + leaf review + CI wait
   + `go` gate cycle.

## §6. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-21 entry
  (line 1714, +33/-0 clarification block + 2
  cross-reference lines).
- `docs/16_audit/BBF-FU-21-impl.md` (the brief whose
  implementation is being clarified).
- `docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md`
  Section B (upstream scoping).
- `services/chess_coach/pdf_ocr/subprocess_runner.py:281`
  (the function the clarification references).
- PR #166 (`BBF-FU-21-impl`, squash `8877ab81`).
- PR #162 (`BBF-doc-drift-flip-3`, the prior
  doc-drift cycle that flipped FU-29 + FU-35).
- PR #165 (`BBF-doc-drift-flip-4`, the prior
  doc-drift cycle that flipped FU-20).
- The forthcoming `BBF-FU-21-windows-scope` brief
  (next BBF in the sequence).
