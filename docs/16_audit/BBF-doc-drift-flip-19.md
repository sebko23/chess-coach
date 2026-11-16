# BBF-doc-drift-flip-19 — scope flip-18's `docs/16_audit/` file count to its pinned base

**Date:** 2026-11-16
**Type:** documentation maintenance (one stale claim in one landed brief)
**Base commit:** `c79c6f4b3f3527811962d72a980b0094a3b32aa4`
**Corrects:** `docs/16_audit/BBF-doc-drift-flip-18.md` §1 item 2

## §1. What this BBF does

`docs/16_audit/BBF-doc-drift-flip-18.md` states, in §1 item 2:

> 91 files under `docs/16_audit/` are tracked on `main`

That sentence was true when flip-18 was written, and became false the moment flip-18
landed — because flip-18's own brief is a file under `docs/16_audit/`.

This BBF scopes the count to an immutable revision instead of to the moving ref. It
changes the scoping of one sentence and nothing else.

## §2. The defect, measured

The count is a property of a directory that the citing document is itself a member of.
Every landing that adds a file under `docs/16_audit/` increments it.

Measured with `git ls-tree -r --name-only <rev> docs/16_audit`:

| Revision | Files tracked under `docs/16_audit/` |
|---|---|
| `42a6a400` (flip-18's pinned base) | 91 |
| `c79c6f4b` (flip-18's landed merge) | 92 |
| the tree this BBF would land | 93 |

The flip-18 brief's own §4 verification table already recorded the base-tree measurement
correctly — its row reads `git ls-tree -r --name-only <base> docs/16_audit` → 91 entries
(90 besides the ledger), and the command names `<base>`. That row was and remains true.

The defect is confined to the §1 prose, which said `` `on `main` `` — a moving ref — where the
table said `<base>` — an immutable one. Two statements of the same fact, only one of them
anchored.

The count value is **not** wrong and is not corrected here. 91 is the true count at the
pinned base. What was wrong was the ref it was attributed to.

## §3. The correction

§1 item 2 now reads, in full:

> 2. **"per the project's `docs/16_audit/` convention."** There is no such
>    convention in the repository's actual state. At the pinned base of this flip,
>    91 files under `docs/16_audit/` were tracked — this ledger among them, plus
>    every per-flip brief in this series. The ledger is tracked alongside them,
>    not apart from them.

Three lines became four; the count value (91) and the sense of the sentence are unchanged.
The past tense ("were tracked") and the explicit ref ("At the pinned base of this flip")
make the measurement a statement about a commit rather than about a branch tip.

## §4. Audit trail

The correction is recorded in the corrected document itself, in flip-18's §8 Honest
limitations, as a `**Correction (2026-11-16, doc-drift flip-19)**` bullet — the correction
convention already used by doc-drift flip-13 in this same brief series. The correction
block names the original wording, the reason it went stale, the two measured counts, and
the fact that the count value itself is unchanged.

## §5. Exact scope

Exactly two files change:

- `docs/16_audit/BBF-doc-drift-flip-18.md`: 14 insertions, 3 deletions — the §1 sentence
  re-scoped (3 lines out, 4 lines in) plus the §8 correction bullet (10 lines added);
- `docs/16_audit/BBF-doc-drift-flip-19.md`: this brief.

No source, test, workflow, configuration, lockfile, or default changes. No runtime
behaviour changes. **The ledger `docs/16_audit/OPEN-FOLLOWUPS.md` is not touched at all**,
so its 3,884-line length and all ten PR #194 pointer values are unaffected by this BBF.

## §6. Verification

- the corrected sentence is present and the original `` `are tracked on `main` `` wording is
  absent from §1; the original wording survives once, inside the §8 correction block's
  quotation of it, which the audit-trail convention requires;

- the count value 91 is unchanged and is still measured against the pinned base;
- `git ls-tree -r --name-only 42a6a400 docs/16_audit` returns 91 entries;
- `git ls-tree -r --name-only c79c6f4b docs/16_audit` returns 92 entries;
- the ledger is byte-identical to its base blob: 3,884 lines, trailing newline intact,
  LF-only, no BOM;
- all ten PR #194 pointer values are unchanged and resolve;
- the only other change to the flip-18 brief is the additive §8 correction bullet;
- `git diff --check` is clean; no file-mode regressions;
- the flip-rules gate passes in manifest mode: scope, numstat, SHA ancestry, and content
  anchors — each anchor verified in its own invocation, because `--anchor` and
  `--preserve` are last-wins flags;
- the gate is proven **non-vacuous**: a wrong numstat, a wrong file set, a wrong anchor,
  and a genuinely non-ancestor SHA are each rejected.

**No runtime test was executed for this change.** The change is prose in two markdown
files with no behavioural surface; every measurement above is a static read of a named
revision.

## §7. Explicit exclusions

- **The flip-18 brief's `**Status:** Draft for review` line.** It is stale — flip-18 is
  merged and CI-verified — but it is a lifecycle marker rather than a factual claim, and
  changing it is a separate wording correction with its own review. It is not changed
  here. The same line is stale in `BBF-doc-drift-flip-16.md` and `BBF-doc-drift-flip-17.md`.
- **The ledger's `2026-11-09` paragraph label.** A separate correction, at a separate
  edit site, with its own line-count consideration.
- **The companion policy file's own "untracked" self-description** in
  `docs/16_audit/HERMES-POLICY-AUTH-BOUNDARIES-2026-08-03.md`. Unchanged by flip-18 and
  unchanged here.
- **The ledger `docs/16_audit/OPEN-FOLLOWUPS.md`.** Not touched; no ledger line changes.
- **The container's and the sibling worktrees' ledger copies.** Outside this repository.

## §8. Honest limitations

- **No runtime test was executed.** The change is prose with no behavioural surface.
- **This BBF does not re-verify anything about the ledger's tracked state.** It corrects
  one sentence's attribution of a count it had already measured.
- **The corrected sentence still contains the number 91.** It is scoped to an immutable
  revision, so it cannot rot, but it remains a number a reader could re-derive and
  disagree with if the pinned base were ever re-interpreted. The command that produced it
  is recorded in flip-18's §8 correction block.
- **This BBF does not claim the flip-18 brief is free of other stale claims.** It
  corrects the one that was measured.
