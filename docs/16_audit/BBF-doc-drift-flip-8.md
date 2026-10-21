# BBF-doc-drift-flip-8 — flip FU-5 + FU-6 to RESOLVED in OPEN-FOLLOWUPS.md

**Sprint intent:** Close the stale headline `**Status:**` lines in
`docs/16_audit/OPEN-FOLLOWUPS.md`:

- **FU-5**: the headline still reads `**Status:** **IN PROGRESS 2026-08-06** by BBF-FU-5 (branch `bbf-fu5-pv-moves-san`, ...)` at post-patch line 206, even though the existing append block at post-patch line 217 already says `**Resolved 2026-08-06 via FU-5 PR #81.**` (pre-patch lines 196 + 207 shifted by +10 for the prepend; the live lines on the post-patch branch head are 206 and 217).
- **FU-6**: the headline still reads `**Status:** OPEN. Low urgency. Not blocking. Pick up after FU-5 ships.` at post-patch line 339, even though the existing append block at post-patch line 341 already says `**Resolved 2026-08-08 via FU-6 PR #82.**` (pre-patch lines 320 + 322 shifted by +19 — +10 for FU-5 prepend + +9 for FU-6 prepend; live lines on the post-patch branch head are 339 and 341). The engine_pool mock landed on `main` via squash `e091988c`.

Both are **truly shipped** ledger-vs-reality gaps — same shape as flip-7's FU-21 closure — but with a twist: the prior `ddeb1e37` (2026-08-10) and `3f3610be` (2026-08-08) doc-drift fix-ups added the *append* Resolved blocks but never corrected the *headline* Status line. The headline-vs-append contradiction is what keeps FU-5/FU-6 reading as IN PROGRESS / OPEN to a casual ledger-grep.

This is the **8th doc-drift flip**. Like flip-7, it closes already-landed work; unlike flip-7, the closure work is *purely bookkeeping* — both implementations are live, both append blocks are accurate, and this flip only repairs the headline-vs-append contradiction by **prepending** a new `**Status (clarified 2026-10-20, doc-drift flip-8): RESOLVED**` block above the existing ones.

**Status:** Doc-only BBF. 2 files modified (`docs/16_audit/OPEN-FOLLOWUPS.md` modified, `docs/16_audit/BBF-doc-drift-flip-8.md` NEW per-flip brief).

---

## §1. The flip pattern (matches BBF-doc-drift-flip-6 and BBF-doc-drift-flip-7)

Per the v0.2.0 clarification pattern (verified PR #93), the flip **prepends** a new `**Status (clarified YYYY-MM-DD, doc-drift flip-N):**` block before the prior flipped append block. All prior Status lines (the original headline + the flip-6/flip-7 versions) are **preserved as historical context**.

For each of FU-5 and FU-6, the new flip-8 block:
- States **RESOLVED 2026-10-20** as the authoritative current state.
- Cites the actual squash SHAs (`cada4ab2` for FU-5, `e091988c` for FU-6) — verified via `git log --all --oneline | grep -E "cada4ab|e091988"`:
  ```
  cada4ab2 feat(gateway): BBF-FU5 additive pv_moves_san field for narration Best Line (#81)
  e091988c test(narration): BBF-FU6 add engine_pool mock to test_narrative_position_fk fixtures (#82)
  ```
- Notes that the flip is *purely a headline-vs-append unification* — the prior append blocks (post-patch lines 217 for FU-5, 341 for FU-6) already say RESOLVED with the same SHAs; flip-8 brings the headline into agreement. (Pre-patch the append blocks were at lines 207 / 322 respectively; the prepends shift them by +10 for the FU-5 prepend and +9 for the FU-6 prepend.)
- Does NOT re-summarize the implementation. The implementation details live in the existing append blocks; flip-8 is meta.

---

## §2. Why both flips in one BBF

The session-startup report named "verify and correct stale FU-5 (and FU-15 and FU-42) ledger statuses" as small-cleanup candidates. FU-6 wasn't named explicitly but is **the same shape** (work shipped, append Resolved block added 2026-08-10, headline untouched) and **the same domain** (narration route). Bundling both in one squashed commit parallels:

- `e4b6738b` (flip-1): flipped 14 stale Status entries in one BBF.
- `3f3610be` (third-round fix-up): added Resolved blocks for FU-5, FU-6, FU-7, FU-8, FU-15, FU-17 in one BBF.

Both precedents establish: doc-drift flip BBFs are the right shape for batched ledger housekeeping; bundling reduces ship-cycle cost.

---

## §3. The two prepended blocks (final shapes on `main`)

### §3.1 FU-5 (after flip)

Above the existing line 206 headline and line 217 append, prepend (line 196 through line 204):

```
**Status (clarified 2026-10-20, doc-drift flip-8):** **RESOLVED
2026-10-20 via squash `cada4ab2`** (PR #81, BBF-FU5 additive
`pv_moves_san` field on `NarrationResponse`). The existing
line-217 append block is accurate; flip-8 only repairs the
headline-vs-append contradiction by promoting the append's
RESOLVED status to the canonical Status section. Implementation
details preserved in the line-217 append below and at
`services/chess_coach/narration/pipeline.py:63` (helper
`_pv_to_san`).
```

### §3.2 FU-6 (after flip)

Above the existing line 339 headline and line 341 append, prepend (line 330 through line 337):

```
**Status (clarified 2026-10-20, doc-drift flip-8):** **RESOLVED
2026-10-20 via squash `e091988c`** (PR #82, BBF-FU6
`engine_pool` mock added to `test_narrative_position_fk`
fixtures). The existing line-341 append block is accurate;
flip-8 only repairs the headline-vs-append contradiction by
promoting the append's RESOLVED status to the canonical Status
section. Implementation details preserved in the line-341
append below.
```

---

## §4. What this BBF does NOT do

- **Does not edit the append blocks.** They're accurate. Re-stating them would be scope-creep.
- **Does not edit FU-2's PARTIAL status.** FU-2 is `PARTIALLY RESOLVED` per line 56, with the live part being the doc-fix in PR #79 and the deferred part being FU-5. Now that FU-5 is RESOLVED, FU-2's PARTIAL wording is technically stale, but FU-2's status shape (`PARTIALLY RESOLVED` per the regex, with one of its sub-parts satisfied by FU-5) is intentionally preserved for now — flagged as a separate potential flip-9 candidate.
- **Does not re-implement either FU-5 or FU-6.** Both ships are on `main`; the on-disk truth is intact.
- **Does not touch FU-15, FU-42.** Those are session-startup-named but are *separate* work items (FU-15 = 3 pre-existing frontend test failures, FU-42 = A-F11 sandbox-isolation tests follow-on to FU-19). Both are still OPEN per the headline and have NO append Resolved block. Different shape from FU-5/FU-6 — out of scope here.

---

## §5. Verifications (live, this session)

- `git rev-parse origin/main` → `c883c3528aeed373809214d8bcff7a0279cd80ef` (HEAD before BBF branch).
- `git ls-files docs/16_audit/BBF-doc-drift-flip-*.md` → confirms flips 3, 4, 6, 7 are tracked (flip-8 will be the 5th tracked flip-brief).
- `git log --all --oneline | grep -E "cada4ab|e091988"` returns the two squashes verbatim, confirming the SHA citations.
- `git log --all --oneline | grep "doc-drift flip"` returns flip-1 through flip-7's commit messages — preserves the naming convention.
- `awk 'NR==196' docs/16_audit/OPEN-FOLLOWUPS.md` (pre-patch) was originally FU-5's headline; the patch prepends 10 lines above it, shifting it to L206. The patched file's anchor pair for FU-5 is now `awk 'NR==196 || NR==217' docs/16_audit/OPEN-FOLLOWUPS.md` (the prepend-line at L196 with the clarified Status header, and the append-block preserved verbatim at L217).
- `awk 'NR==320 || NR==322' docs/16_audit/OPEN-FOLLOWUPS.md` (pre-patch) was originally FU-6's headline+append pair; the patch prepends +10 + +9 = +19 lines, shifting them to L339 and L341 respectively. The patched file's anchor pair for FU-6 is now `awk 'NR==330 || NR==341' docs/16_audit/OPEN-FOLLOWUPS.md` (the prepend-line at L330 with the clarified Status header, and the append-block preserved verbatim at L341).
- `wc -l docs/16_audit/OPEN-FOLLOWUPS.md` → `3124` lines before patch, `3143` lines after patch (+19 = +10 FU-5 prepend + +9 FU-6 prepend; verified at session-open and post-patch).

Pre-commit hygiene (per `references/pre-squash-commit-hygiene.md`):
- Branch created from `main` with no prior commits on it (`git log origin/main..HEAD --oneline` will show exactly 1 commit after `commit`).
- The commit body's prose describes the **final on-main shape** (numstat vs `origin/main`).
- No `--force-with-lease`; this is a fresh branch.

---

## §6. Cross-references

- `docs/16_audit/BBF-doc-drift-flip-7.md` (parent flip, squash `c883c352`, PR #170) — the immediate prior precedent.
- `docs/16_audit/BBF-doc-drift-flip-6.md` (flip-6, squash `a670cd79`, PR #165) — the first to introduce the `Status (clarified YYYY-MM-DD)` prepended-block pattern.
- `docs/16_audit/OPEN-FOLLOWUPS.md` lines 196-217 (FU-5 region: prepend + headline + preserved append; live on the branch head) and lines 330-341 (FU-6 region: prepend + headline + preserved append; live on the branch head) — the targets.
- `services/chess_coach/narration/pipeline.py:63` — the `_pv_to_san` helper shipped by BBF-FU5 (FU-5 implementation evidence).
- `tests/integration/test_narrative_position_fk.py` — the fixture file BBF-FU6 modified (FU-6 implementation evidence; specific fixture changes verified via `git show e091988c --stat`).
- `git log --all --oneline | grep -E "cada4ab|e091988"` — the SHA source of truth.

---

## §7. Pre-leaf-review checklist (for the next session's reviewer)

Per `references/decision-only-bbf-leaf-review.md`:

1. **Numstat:** `git diff --numstat origin/main..HEAD` should show **2 files changed: `125  0   docs/16_audit/BBF-doc-drift-flip-8.md` + `19  0   docs/16_audit/OPEN-FOLLOWUPS.md` = `2 files, 144 insertions(+), 0 deletions(-)`**. The 19 ledger insertions split as 10 (FU-5 prepend, lines 196-204 + blank separator) + 9 (FU-6 prepend, lines 330-337 + blank separator). The brief's own 125 lines contribute the rest. **NOT** "1 file changed, 24 insertions" — that was an author-side arithmetic guess that does not match the live tree.
2. **Headline-vs-append unification:** the prepended block uses the verbatim wording in §3.1 and §3.2 above. Verify by reading lines 196-217 (FU-5 region: prepend + blank separator + headline + first lines of preserved append) and lines 330-341 (FU-6 region: prepend + blank separator + headline + first lines of preserved append) after patch.
3. **SHA citation accuracy:** `cada4ab2` and `e091988c` resolve via `git log --all --oneline | grep -E "cada4ab|e091988"` to the verbatim messages cited above.
4. **Convention self-application:** the `Status (clarified YYYY-MM-DD, doc-drift flip-N):` pattern matches flip-6 (the originator) and flip-7 (the immediate prior). This is the **8th** flip in the chain; the numbering is consistent.
5. **No scope creep:** §4 lists what flip-8 does NOT do. Each NON-do item is verifiable as not-done in the post-patch diff.
6. **Pre-PR cross-reference verification (per v0.7.124):** every `path:NNN` and SHA citation in this brief must resolve against the live tree. All such citations verified at session-open; no drift expected (per §5).
