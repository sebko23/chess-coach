# Doc conventions — chess-coach

**Status:** Living document. Conventions for `*.md` files in this repo, especially
"current state" docs that describe the project as it stands today. Authored 2026-08-04
during the doc-reconciliation BBF after a leaf reviewer flagged 12 fabricated commit
SHAs in `docs/01_architecture/system-architecture.md` that the prior BBF inherited
from a 2026-06-20 snapshot.

**Scope:** applies to README.md, `docs/01_architecture/system-architecture.md`,
`docs/01_architecture/*.md`, and any future "current state" doc. Does NOT apply to
dated audit snapshots (e.g. `docs/16_audit/project-audit-2026-06-14.md`), where
citing a historical commit is the entire point.

---

## SHA citations in current-state docs: avoid or qualify

**Rule:** A "current state" doc that describes the project as it stands today
should not cite raw commit SHAs as evidence for present-tense claims, unless the
SHA is currently reachable in `git log --all --reflog`.

**Why:** The project uses squash-merge-per-BBF (`docs/01_architecture/system-architecture.md`
references this convention; also per the BBF-shipping skill). When a squash
commit is the merge commit, the underlying feature-branch commits get
squashed away and become unreachable. SHAs that were valid in a prior doc are
silently invalidated by future squash-merges — `git cat-file -t <sha>` returns
"Not a valid object name" for them.

**What to do instead:**

1. **Describe the substance, not the SHA.** "The narration route invokes
   `engine_pool.analyze()`" — a current-state claim backed by a file:line
   citation that resolves today. No SHA needed.

2. **If a specific commit needs referencing** (e.g. "the original YOLOv8
   detection commit"), qualify it as a point-in-time reference as of the doc's
   own date stamp: "as of 2026-06-14, this work landed in commit `<sha>` (point-in-time
   reference; may no longer be reachable in the current history)." The reader is
   warned that the SHA is a snapshot, not a present-tense anchor.

3. **For current BBFs on `main`, the squash SHAs are usually reachable** —
   `git log --oneline` will show them. Use them freely, but verify with
   `git cat-file -t <sha>` before publishing.

**Pre-verify reflex:** before merging any doc PR, sample 3-5 cited SHAs and
verify each with `git cat-file -t <sha>`. If any returns "Not a valid object
name", that's a BLOCKER.

---

## Cross-references: prefer file:line over SHA

**Rule:** For current-state claims, prefer `path/to/file.ext:NNN` citations
over commit SHAs. File:line citations are stable across squash-merges (the
file may move, but the contents are verifiable at any time via `git show`).

**Why:** same reason as the SHA rule — squash-merges invalidate SHAs, file:line
is durable.

---

## Duplicate doc copies: mark canonical vs snapshot explicitly

**Rule:** When the same doc appears in two locations (e.g.
`docs/01_architecture/system-architecture.md` and a review snapshot at
`docs/12_claude_review/fable5-prompt1-ready-to-paste.md`), the header of each
copy should declare:

1. Which is canonical (the doc-of-record that future changes apply to).
2. Which is a historical snapshot (frozen at the date stated).
3. A cross-reference linking the two.

**Why:** Otherwise readers don't know which copy is current, and the two
silently drift.

---

## Doc-only PRs: same verification standard as code PRs

**Rule:** Doc-only PRs are still PRs. They need:

1. Leaf review (via `delegate_task` with the standard template).
2. CI green (no behavioral change, but CI still runs the security/secret/lockfile jobs).
3. Explicit squash-merge authorization from the user (full-sentence confirmation
   naming the action and PR number). Bare short-form replies are NOT authorization.
4. Real pytest verification of any test changes; real file:line verification of
   any factual claims.

**Why:** Docs are load-bearing for new contributors and for the audit trail.
"Factual claim, no verification" is a regression-class defect for a doc.

---

**End of doc conventions.**
