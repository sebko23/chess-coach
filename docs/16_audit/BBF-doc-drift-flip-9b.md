# BBF-doc-drift-flip-9b — retire FU-17's stale mid-entry `Status: OPEN` block (shape A)

**Sprint intent:** Retire the stale `**Status:** OPEN. Moderate priority.` block buried mid-entry in the FU-17 section of `docs/16_audit/OPEN-FOLLOWUPS.md`, replacing it with a one-line pointer to the facts already recorded in the same entry.

**This is the 9b flip** (the `b` sibling of flip-9a, which handled FU-15). Like flip-6/7/8/9a, it closes already-landed work. FU-17's durable-pnpm-pin implementation shipped 2026-08-09 via PR #87 (squash `20792f48`); the entry's top-of-headline status already says RESOLVED (L1357) and an accurate append exists at L1409. The only remaining inconsistency is the orphaned `OPEN` block.

**Status:** Doc-only BBF. 2 files (`docs/16_audit/OPEN-FOLLOWUPS.md` modified, `docs/16_audit/BBF-doc-drift-flip-9b.md` NEW per-flip brief).

---

## §1. Why shape A (and why flip-9b is not shape B-on-the-headline)

The session hypothesis for flip-9b was "mirror flip-9a: replace a stale headline status with a pointer." **Live inspection refuted that.** FU-17's structure differs materially from FU-15's:

| Region | FU-15 (flip-9a) | FU-17 (flip-9b) |
|---|---|---|
| Top-of-entry status | `PARTIAL` — **stale** (L1227 on the pre-#172 tree `12d4962e`; on this branch's base `7ffe9f1c` that line already reads `RESOLVED`, flipped by PR #172) | `**RESOLVED 2026-08-09 via squash-merge of PR #87**` — **already correct** (L1357) |
| Stale `OPEN`/`PARTIAL` block | at top of entry | **mid-entry**, below the "Suggested fix approach" section (pre-patch L1407–L1411) |
| Accurate append | none of its own; pointed at a clarification block | `**Resolved 2026-08-09 via FU-17 PR #87.**` (post-patch L1409) |
| Clarification block | 9-line, `Status (clarified 2026-08-10, …)` | 9-line, `Status (clarified 2026-08-11, …)` |

FU-17's entry already *leads* with a correct RESOLVED headline. The stale `OPEN` block is historical text sitting between the "Suggested fix approach" list and the accurate append. Shape A therefore targets that mid-entry block specifically — not the entry headline — and replaces it with a one-line pointer.

**Rejected alternatives:**

- **Shape B (also correct the clarification's "at the top of this entry"):** semantically cleaner, but it edits the clarification block. flip-6/7/8/9a all preserved clarification/append blocks byte-identical; editing one would weaken that gate for no ledger-reading benefit, since a casual grep already sees `RESOLVED` at L1357 and at the new pointer.
- **Shape C (delete L1407–L1411 outright):** a pure ledger deletion. It would falsify the clarification block's explicit claim that "the original `Status: OPEN. Moderate priority.` block … is preserved as historical context," and it breaks the zero-deletion-on-preserved-content invariant that every prior flip honored.
- **Shape D (no-op):** the stale `OPEN` is grep-visible (`grep "Status: OPEN"` hits this line), so leaving it re-introduces exactly the class of confusion flip-9a just fixed for FU-15.

**Disclosure (deliberately not fixed in this flip):** the preserved clarification block at post-patch L1445 still says *"at the top of this entry."* That was accurate when written (2026-08-11), but a RESOLVED headline has since been inserted above it, so the phrase is now historically-imprecise. Per authorization, this flip **does not alter it** — the phrase is preserved byte-for-byte and its imprecision is documented here in the brief rather than in the ledger. A future flip may correct the wording if the byte-identical gate is ever relaxed for clarification blocks.

---

## §2. The replacement (final shape on `main`)

Pre-patch `docs/16_audit/OPEN-FOLLOWUPS.md` lines 1407–1411 (on this branch's base `7ffe9f1c`; the range was 1408–1412 on the pre-#172 tree `12d4962e`):

```
**Status:** OPEN. Moderate priority. Same threshold-3-driven urgency
as the other FU-13-promoted structural fixes. Not blocking the FU-14
PR merge (FU-14's path-1 patch-around is the correct contained fix
for the immediate failure), but should be addressed before the next
JS-dep-related BBF to avoid the next patch-around.
```

replaced by one line (post-patch L1407):

```
**Status:** RESOLVED 2026-08-09 via FU-17 PR #87 (`20792f4`); see the preserved clarification below.
```

Ledger delta: `+1 / −5` = net −4 lines (`3142` → `3138`). Everything else in the FU-17 entry is byte-identical: the top-of-entry RESOLVED headline (L1357), the "Suggested fix approach" list (L1389–L1405), the accurate append (L1409), and the 2026-08-11 clarification block (L1441–L1449).

---

## §3. What this BBF does NOT do

- **Does not touch the FU-17 top-of-entry headline at L1357.** Already correct; verbatim preserved.
- **Does not touch the FU-17 append block at L1409.** Accurate; verbatim preserved.
- **Does not touch the 2026-08-11 clarification block at L1441–L1449.** Byte-identical, verified by direct `diff` against `main`.
- **Does not correct the clarification's "at the top of this entry" phrasing.** Deliberate; documented in §1 per authorization.
- **Does not touch FU-15.** Closed by flip-9a (`dd91d97f`, local-only).
- **Does not touch any source, lockfile, package.json, or CI workflow.** Doc-only BBF.

---

## §4. Verifications (live, this session)

- Base (at authoring): `main` → `12d4962ebe5bf08998adf01e8d57e67bf96271e7` (PR #171 merge commit). **Rebased onto `main @ 7ffe9f1c93603511d87f243cb18d8d73abefca4d`** (PR #172 merge commit) before publication; PR #172 removed one ledger line above FU-17, so every FU-17 anchor cited here is numbered against the post-#172 tree. Branch `bbf-doc-drift-flip-9b` created from it; `git rev-parse --verify bbf-doc-drift-flip-9b` did not exist beforehand.
- SHA citations resolved via `git log --all --oneline`:
  ```
  20792f48 fix(deps): FU-17 durable pnpm pin via packageManager + corepack (#87)  [2-parent merge: 7c1d5d4e + 356f532b]
  ddeb1e37 docs(OPEN-FOLLOWUPS): add missing Resolved blocks for FU-5 + FU-17 (#91)  [2-parent merge]
  3f3610be docs(OPEN-FOLLOWUPS): third-round doc-drift fix-up (FU-6, FU-7, FU-8, FU-15, FU-17) (#93)  [2-parent merge: ef3bda74 + 7f775b31]
  ```
- `git rev-parse --short=7 20792f48` → `20792f4`, matching the SHA cited in the new pointer and in the preserved append at L1411.
- `git diff --numstat` (ledger only, pre-brief) → `1 5 docs/16_audit/OPEN-FOLLOWUPS.md`.
- `wc -l docs/16_audit/OPEN-FOLLOWUPS.md` → `3138` post-patch (`3142` pre-patch; net −4 = −5 removed +1 added).
- `wc -l docs/16_audit/BBF-doc-drift-flip-9b.md` → `110`; `git diff --cached --numstat` → `111 0` for this file, because it has **no trailing newline** (last byte is `.`, confirmed via `od -c`), so `wc -l` undercounts by one. **Reviewers must use git's numstat (`111 0`), not `wc -l`.** Not borrowed from flip-9a's 117 or flip-8's 125.
- Clarification byte-integrity: `git show origin/main:docs/16_audit/OPEN-FOLLOWUPS.md | sed -n '1445,1453p'` diffed against post-patch `sed -n '1441,1449p'` → **no differences** (byte-for-byte identical).
- Post-patch anchors: L1357 = `**Status:** **RESOLVED 2026-08-09 via squash-merge of PR #87**` (unchanged); L1407 = new pointer; L1409 = `**Resolved 2026-08-09 via FU-17 PR #87.**` (unchanged); L1441 = `**Status (clarified 2026-08-11, third-round doc-drift fix-up):**` (unchanged).
- No tracked file outside `docs/16_audit/` modified. No `??` debris staged.

Pre-commit hygiene:

- Fresh branch, zero prior commits (`git log origin/main..HEAD --oneline` empty pre-commit).
- Commit Author and Committer both forced via `git -c user.name='Sebastian Wasielewski' -c user.email='lesson@o2.pl'` (session git config is `Hermes Agent <hermes@nousresearch.com>`; matching PR #171's pair is required for history consistency).
- No force operations.

---

## §5. Cross-references

- `docs/16_audit/BBF-doc-drift-flip-9a.md` (sibling flip; FU-15 headline `PARTIAL` → pointer) — same class, `bbf-doc-drift-flip-9a` branch, local commit `dd91d97f`, **not yet pushed**.
- `docs/16_audit/BBF-doc-drift-flip-8.md` (flip-8, single-parent squash `12d4962e`, PR #171) — immediate prior precedent, same ledger; its parent is `c883c352`.
- `git show 20792f48 --no-patch --format='%H %s'` — FU-17 implementation squash (source of truth for `20792f4`).
- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-17 region: headline L1357, suggested-fix list L1389–L1405, new pointer L1407, append L1409, clarification L1441–L1449 (all post-flip-9b numbering).
- FU-13 (same ledger) — the threshold tracker whose 3/3 crossing promoted FU-17.

---

## §6. Pre-leaf-review checklist (for the next session's reviewer)

1. **Numstat:** `git diff --numstat origin/main..HEAD` should show **2 files changed**, with the ledger at **`1 5`** and the brief at its actual line count (this file's own `wc -l` at review time — do not assume it matches flip-9a's 117 or flip-8's 125).
2. **Headline coherence:** post-patch L1357 (`RESOLVED` via PR #87) and post-patch L1407 (pointer) both read RESOLVED. `grep "Status: OPEN" OPEN-FOLLOWUPS.md` no longer matches the FU-17 **status line**; it still matches once inside the FU-17 entry, in the preserved 2026-08-11 clarification block, which quotes that text as history (disclosed in §1). No second LIVE-marker block was added.
3. **SHA accuracy:** `20792f4` resolves via `git log --all --oneline | grep FU-17` to squash `20792f48` (PR #87).
4. **Byte-identical preservation:** the 2026-08-11 clarification block (post-patch L1441–L1449) and the FU-17 append (L1409) are unchanged from `main`; verify with `git diff main -- docs/16_audit/OPEN-FOLLOWUPS.md` showing a single 5-line→1-line hunk.
5. **Convention self-application:** the brief discloses the clarification's now-imprecise "at the top of this entry" phrasing (§1) instead of silently editing it.
6. **No scope creep:** §3 lists what flip-9b does NOT do; each is verifiable as not-done in the diff.
7. **Pre-PR cross-reference verification (v0.7.124):** every `path:NNN` and SHA above resolves against the live tree.
8. **Identity:** Author and Committer are both `Sebastian Wasielewski <lesson@o2.pl>`, matching PR #171.