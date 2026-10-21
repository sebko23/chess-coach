# BBF-doc-drift-flip-9a — flip FU-15 headline `PARTIAL` → `RESOLVED` in OPEN-FOLLOWUPS.md (shape B)

**Sprint intent:** Close the stale headline `**Status:** PARTIAL` line in `docs/16_audit/OPEN-FOLLOWUPS.md` for FU-15.

- **FU-15**: the headline at pre-patch line 1227 still reads `**Status:** PARTIAL — Test 4 resolved 2026-08-09 (PR #86). Tests 1-3 deferred as FU-16.`, even though the existing clarification block at post-patch lines 1229–1237 already declares the LIVE status as `**FULLY RESOLVED 2026-08-10 via PR #86 (Test 4) + PR #89 (Tests 1-3, deferred as FU-16).**` (pre-patch lines 1230–1238; the single-line shrink of the `-2/+1` replacement shifts them up by 1 to L1229–1237 on the post-patch branch head).

This is the **9th doc-drift flip** (the `a` in `9a` reserves the slot for a hypothetical FU-17 same-shape flip in flip-9). Like flip-6/7/8, it closes already-landed work. **Unlike flip-6/7/8, the existing body already carries a full clarification block dated 2026-08-10** (`Status (clarified 2026-08-10, third-round doc-drift fix-up): FULLY RESOLVED …`). The naive analog of flip-8 (prepend a *second* `Status (clarified 2026-10-21, flip-9a)` block) would produce **two parallel LIVE-marker blocks dated 2026-08-10 and 2026-10-21**, retroactively obsoleting the original 2026-08-10 clarification by existing — which violates the "preserved append byte-identical" invariant at the meta-level.

The flip-9a shape is therefore **shape B**: replace the stale 2-line `PARTIAL` headline with a single line that points at the existing 2026-08-10 clarification block. The clarification block at L1229–1237 is preserved byte-identical and becomes the canonical LIVE marker (which it already self-declares as).

**Status:** Doc-only BBF. 2 files modified (`docs/16_audit/OPEN-FOLLOWUPS.md` modified, `docs/16_audit/BBF-doc-drift-flip-9a.md` NEW per-flip brief).

---

## §1. Why shape B and not the flip-8 prepended-block pattern

Per the v0.2.0 clarification pattern (verified PR #93), flip-6 was the first to prepend a `**Status (clarified YYYY-MM-DD, doc-drift flip-N):**` block above the original headline. flip-7 and flip-8 followed the same shape because their targets (FU-21, FU-5, FU-6) had an accurate **append** Resolved block but no inline clarification.

FU-15's situation is **materially different**: the 2026-08-10 third-round doc-drift fix-up (squash `3f3610be`, PR #93) already added a 9-line clarification block at L1229–1237 (pre-patch L1230–1238) whose own text reads:

> The original PARTIAL status line is preserved as historical context; the LIVE status is the FULLY RESOLVED line below.

Doing a literal flip-8 analog here would:

1. Produce two parallel blocks both claiming to be the LIVE marker.
2. Make the 2026-08-10 clarification's self-declaration ("preserved as historical context") true only because the 2026-10-21 block re-defined what "LIVE" means — i.e., the new block would retroactively flip the meaning of the existing block.
3. Add ~9 lines that duplicate content already present.

Shape B replaces the now-misleading 2-line `PARTIAL` headline with a single line that:
- States the LIVE status (`RESOLVED 2026-08-10`).
- Cites the actual squash SHAs (PR #86 = squash `fbf874de`, PR #89 = squash `77a83796`) and landing dates (2026-08-09 and 2026-08-10 respectively).
- Points at the existing clarification block by saying `See clarification below.` — preserving every existing byte of that block, including its self-declared status-as-LIVE function.

Net ledger effect: `-2 +1 = -1` line, the clarification block becomes the canonical LIVE marker, the headline agrees with the body.

---

## §2. The single-line replacement (final shape on `main`)

At `docs/16_audit/OPEN-FOLLOWUPS.md` line 1227 (post-patch), the new headline reads:

```
**Status:** RESOLVED 2026-08-10 via PR #86 (Test 4, landed 2026-08-09) + PR #89 (Tests 1-3, deferred as FU-16, squash `77a8379`, landed 2026-08-10). See clarification below.
```

Pre-patch lines 1227–1228:

```
**Status:** PARTIAL — Test 4 resolved 2026-08-09 (PR #86). Tests 1-3
deferred as FU-16.
```

are replaced with the one-line shape above. The clarification block at post-patch L1229–1237 (pre-patch L1230–1238) is **byte-identical preserved** — no edits inside the `Status (clarified 2026-08-10, third-round doc-drift fix-up):` block.

---

## §3. What this BBF does NOT do

- **Does not edit the 2026-08-10 clarification block.** It's the canonical LIVE marker and is preserved byte-identical.
- **Does not delete the "PARTIAL" wording entirely.** Replacing the 2-line headline with a single RESOLVED line that *contains* the dates and PR numbers inherently retires the misleading "PARTIAL" framing; further deletion would be destructive beyond scope.
- **Does not touch FU-17.** It has the same shape (stale `Status: OPEN` headline + accurate 2026-08-11 clarification block) and is a flip-9b candidate. Out of scope here.
- **Does not edit FU-2's PARTIALLY RESOLVED status.** FU-2 is `PARTIALLY RESOLVED` per line 56, with the live part being the doc-fix in PR #79 and the deferred part being FU-5. Now that FU-5 is RESOLVED, FU-2's PARTIAL wording is technically stale, but FU-2's status shape (`PARTIALLY RESOLVED` per the regex, with one of its sub-parts satisfied by FU-5) is intentionally preserved for now — flagged as a separate potential flip-9 candidate. (Verbatim from `BBF-doc-drift-flip-8.md:82`; flip-8 deliberately did not close FU-2.)
- **Does not touch FU-5, FU-6, FU-21.** FU-5/FU-6 were closed by **flip-8** (`12d4962e`, PR #171); FU-21 was closed by flip-6 (`1487ff76`, PR #167) and flip-7 (`c883c352`, PR #170). None of their appends are byte-identical preserved by *this* flip; they remain as those earlier flips left them.
- **Does not re-implement FU-15.** Its ships are on `main`; the on-disk truth (`apps/desktop/src/components/panels/coach/CoachPanel.test.tsx` no longer contains the rail-mode test; `apps/desktop/src/components/panels/profile/ProfileDashboard.test.tsx` uses `@testing-library/react`) is intact.
- **Does not touch any tracked file outside `docs/16_audit/`.** This is a doc-only BBF; no source, no lockfile, no CI workflow touched.

---

## §4. Verifications (live, this session)

- `git rev-parse origin/main` → `12d4962ebe5bf08998adf01e8d57e67bf96271e7` (HEAD before BBF branch; PR #171 merge commit per `git show 12d4962e --stat`).
- `git ls-files docs/16_audit/BBF-doc-drift-flip-*.md` → confirms flips 3, 4, 6, 7, 8 are tracked (flip-9a will be the 6th tracked flip-brief).
- `git log --all --oneline | grep -E "fbf874de|77a83796"` returns the two squashes verbatim:
  ```
  fbf874de fix(deps): FU-14 js-yaml fix + FU-15 Test 4 fix + OPEN-FOLLOWUPS entries (pnpm 10 path-1)
  77a83796 fix(tests): FU-16 ProfileDashboard async-data test fix (@testing-library/react)
  ```
- `git rev-parse --short=7 77a83796` → `77a8379` (matches the SHA cited in the existing L1234 clarification block and in the new headline).
- `git diff --numstat origin/main..HEAD` (post-patch, post-add) → expected: `118 0 docs/16_audit/BBF-doc-drift-flip-9a.md` + `1 2 docs/16_audit/OPEN-FOLLOWUPS.md` = `2 files, 119 insertions(+), 2 deletions(-)`. (Brief is 118 lines; the flip-8 brief was 125 lines — flip-9a is smaller because shape B is a 1-line replacement, not a 9-line prepend, so the brief is too.) The ledger change is `+1/-2` = net `-1` line, all from the FU-15 headline region; no other line moves.
- `wc -l docs/16_audit/OPEN-FOLLOWUPS.md` → `3143` lines pre-patch (post-#171), `3142` lines post-patch (`-1` confirmed; the clarification block's pre-patch L1230–1238 shifts to L1229–1237).
- `awk 'NR==1216 || NR==1239' docs/16_audit/OPEN-FOLLOWUPS.md` (post-patch) → returns the `**Resolved partially 2026-08-09 via FU-14 PR #86.**` lead-in (L1216) and the `**Cross-references:**` section header (L1239, was pre-patch L1240 before the `-1` line shift). Both byte-identical to their pre-patch contents: pre-patch L1216 = `**Resolved partially 2026-08-09 via FU-14 PR #86.**`; pre-patch L1240 = `**Cross-references:**`. The `awk` call confirms no body content shifted unexpectedly.
- Surrounding-window sanity: lines 1216–1225 (paragraph "Resolved partially 2026-08-09 via FU-14 PR #86.") are byte-identical preserved; lines 1229–1248+ are byte-identical preserved relative to pre-patch lines 1230–1249+ (after the `-1` shift).
- No `??` debris added by this BBF. The brief is a NEW tracked file (`git add`); the ledger M is unchanged from session open.

Pre-commit hygiene (per `references/pre-squash-commit-hygiene.md`):

- Branch created from `main` with no prior commits (`git log origin/main..HEAD --oneline` shows exactly 1 commit after `commit`).
- Commit Author is forced via `git -c user.name='Sebastian Wasielewski' -c user.email='lesson@o2.pl' commit …` per the project identity (matches PR #171 / PR #165 / PR #170 authors).
- The commit body describes the **final on-main shape** (numstat vs `origin/main`), not the working-tree state.
- No `--force-with-lease`; this is a fresh branch.

---

## §5. Cross-references

- `docs/16_audit/BBF-doc-drift-flip-8.md` (immediate prior, squash `12d4962e`, PR #171) — same class, prepend-block shape; flip-9a deviates intentionally because FU-15 already has a clarification block.
- `docs/16_audit/BBF-doc-drift-flip-6.md` (flip-6, merge `1487ff76`, PR #167) — originator of the `Status (clarified YYYY-MM-DD)` pattern; not directly applicable to flip-9a's shape-B because FU-15's body already carries the clarification.
- `docs/16_audit/BBF-doc-drift-flip-7.md` (flip-7, squash `c883c352`, PR #170) — same prepend-block shape as flip-8.
- `docs/16_audit/OPEN-FOLLOWUPS.md` lines 1216–1248 (FU-15 region: resolved-partially preamble + new RESOLVED headline + preserved 2026-08-10 clarification block + cross-references; live on the branch head).
- `git show fbf874de --no-patch --format='%H %s'` — FU-15 Test 4 fix (CoachPanel rail-mode test deletion) squash source of truth. `fbf874de` is a genuine single-parent squash (parent `5309624e`); the PR #86 merge commit on `main` is `7c1d5d4e` (parents `5309624e` + `fbf874de`). For PR #89 and PR #93 the merge commit *is* the cited SHA (`77a83796` has parents `dece5548` + `962e7486`; `3f3610be` has parents `ef3bda74` + `7f775b31`), so "squash" in the ledger's existing text is accurate for those two. The zero-parameter export `export default function CoachPanel()` is at `apps/desktop/src/components/panels/coach/CoachPanel.tsx:304` on the branch head.
- `git show 77a83796 --no-patch --format='%H %s'` — FU-15 Tests 1-3 fix (ProfileDashboard async-data via `@testing-library/react`) squash source of truth; squashed under FU-16 since the three tests were deferred there.
- `git show 12d4962e --format='%H %s'` — prior `main` HEAD before this BBF; preserves the "before" anchor.
- `git log --all --oneline | grep -E "fbf874de|77a83796"` — SHA source of truth (also `git rev-parse --short=7` for short-form verification).

---

## §6. Pre-leaf-review checklist (for the next session's reviewer)

Per `references/decision-only-bbf-leaf-review.md` and the v0.7.107 / v0.7.124 / v0.7.126 gates:

1. **Numstat:** `git diff --numstat origin/main..HEAD` should show **2 files changed: `118  0   docs/16_audit/BBF-doc-drift-flip-9a.md` + `1  2   docs/16_audit/OPEN-FOLLOWUPS.md` = `2 files, 119 insertions(+), 2 deletions(-)`**. (Flip-8's brief was 125 lines / 144 insertions; flip-9a is smaller because FU-15 already carries the clarification block and shape B is a 1-line replacement, not a 9-line prepend.)
2. **Headline agrees with body:** post-patch L1227 starts with `**Status:** RESOLVED 2026-08-10`. Post-patch L1229 starts with `**Status (clarified 2026-08-10, third-round doc-drift fix-up):**`. Both are RESOLVED; the headline points to the body. No contradiction.
3. **SHA citation accuracy:** `fbf874d` (PR #86) and `77a8379` (PR #89) resolve via `git log --all --oneline | grep -E "fbf874de|77a83796"` to the verbatim squashes cited in §4.
4. **Convention self-application:** the brief uses shape B (replace headline, preserve clarification) — the same `Status (clarified YYYY-MM-DD)` text that the clarification block already uses is left in place; no parallel LIVE-marker block is added. This is the deviation from flip-8 documented in §1.
5. **No scope creep:** §3 lists what flip-9a does NOT do. Each NON-do item is verifiable as not-done in the post-patch diff.
6. **Pre-PR cross-reference verification (per v0.7.124):** every `path:NNN` and SHA citation in this brief must resolve against the live tree. All such citations verified at session-open; no drift expected (per §4).
7. **Author / committer identity:** this branch's commit has Author **and** Committer both `Sebastian Wasielewski <lesson@o2.pl>` (per the `-c user.name=…` / `-c user.email=…` overrides on the `git commit` invocation). Note that this does **not** match the committer on the prior flip merges: PRs #171 (`12d4962e`), #170 (`c883c352`), #167 (`1487ff76`) and #165 (`4b071599`) all have Author `Sebastian Wasielewski <lesson@o2.pl>` but Committer `GitHub <noreply@github.com>`, because those were squash-merged through the GitHub UI. The Author identity is consistent across the chain; the Committer differs by mechanism (UI squash-merge vs local commit + push), which is expected rather than a discrepancy.
8. **Ledger delta vs `main @ 12d4962e`:** net `-1` line on OPEN-FOLLOWUPS.md (3143 → 3142), `+118` lines on the NEW brief, no other tracked file touched. Verified via `wc -l` and `git diff --numstat` at session-open and post-add.
