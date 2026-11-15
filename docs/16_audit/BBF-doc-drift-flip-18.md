# BBF-doc-drift-flip-18 — correct the ledger's stale "this file is untracked" header

**Status:** Draft for review
**Base:** `42a6a400cf37911d15dc8edcd744000945c6fcdc`

## §1. Why this flip exists

The ledger's own preamble told every future session a false thing about the file
they were reading:

```text
**Convention:** This file is untracked, per the project's `docs/16_audit/` convention.
Do NOT `git add` it. Future sessions should read this on startup alongside
`HERMES-POLICY-AUTH-BOUNDARIES-2026-08-03.md`.
```

Three claims in three lines, and all three were false against the repository:

1. **"This file is untracked."** The file is tracked. It has been in git since
   2026-08-08, when squash `7180433e` (PR #84) added it with 892 insertions.
   `git ls-files --error-unmatch` resolves it; `git check-ignore` does not match
   it, so it is not ignored either.
2. **"per the project's `docs/16_audit/` convention."** There is no such
   convention in the repository's actual state. 91 files under `docs/16_audit/`
   are tracked on `main` — this ledger among them, plus every per-flip brief in
   this series. The ledger is tracked alongside them, not apart from them.
3. **"Do NOT `git add` it."** An instruction to avoid a no-op. The file is
   already in the index on every branch derived from the pinned base.

The header became false on 2026-08-08. Every doc-drift flip since then
edited this file **as a tracked file** — the flips *are* the commits that
modified it — and every one of them preserved the header untouched as
protected prose, which is why the false claim survived every one of them.

A stale instruction to future agents is not a cosmetic defect. A session that
believed this file was untracked would treat it as a local scratch artifact —
would not commit corrections to it, would not cite it as authoritative, and
would not expect `git diff` to show its changes.

## §2. The correction

Three lines are replaced by three lines. The line count is unchanged, so every
`path:NNN` anchor and every PR #194 pointer below shifts by zero.

```text
**Convention:** This file is tracked in git and has been since 2026-08-08 (PR #84). Do NOT
remove it or add it to `.gitignore`; future sessions should read this on startup alongside
`docs/16_audit/HERMES-POLICY-AUTH-BOUNDARIES-2026-08-03.md`.
```

Three changes are made deliberately:

- **"untracked" → "tracked in git and has been since 2026-08-08 (PR #84)".** The
  corrected claim carries the date and the PR, so a reader can see *when* the
  old convention ended rather than only that it did.
- **"Do NOT `git add` it" → "Do NOT remove it or add it to `.gitignore`".** The
  original instruction guarded against a mistake that is no longer possible.
  The new one guards against the mistake that *is* possible now: this file is
  tracked, so a future session could remove it or add it to `.gitignore` under
  the belief that `docs/16_audit/` files are meant to be untracked.
- **The policy file's path gains its directory prefix.** The old line cited
  `` `HERMES-POLICY-AUTH-BOUNDARIES-2026-08-03.md` `` as a bare filename. The
  file actually lives at `docs/16_audit/HERMES-POLICY-AUTH-BOUNDARIES-2026-08-03.md`.
  This matters mechanically: `scripts/dev/verify_commit_refs.py` resolves a bare
  `.md` name **at the repository root**, where no such file exists. A bare name
  is therefore rejected only when it is **unbackticked and carries a line
  number** — then it is reported as a bare-file reference under the
  path-qualification discipline. A bare name that is backticked, or that
  carries no line number, is not parsed as a reference at all and passes
  vacuously. The corrected citation carries the directory prefix and resolves
  in every form.

## §3. Why line-count neutrality is load-bearing here

PR #194 landed ten `**Original entry:** lines N-M` pointers in this same ledger
whose values are line numbers. All ten sit below this header, so a net line
change here would silently re-point them at the wrong entries — the defect
class PR #194 was merged to fix, and one no CI gate in this repository can
catch.

The edit is line-count neutral **by construction**: three lines replaced by
three lines. The ledger stays at **3,884 lines** with its trailing newline
intact, and exactly **three** lines differ from the base. All ten pointer
values are unchanged and still resolve.

## §4. What was measured

Every claim in the corrected header was measured against the base tree, not
inferred from the ledger's own prose:

| Claim | Measured |
|---|---|
| the file is tracked | `git ls-files --error-unmatch docs/16_audit/OPEN-FOLLOWUPS.md` → resolves |
| it is not ignored | `git check-ignore -v docs/16_audit/OPEN-FOLLOWUPS.md` → exit 1, no match |
| it has been tracked since 2026-08-08 | `git log --diff-filter=A` → `7180433e73d2…` (PR #84, 2026-08-08) |
| 91 `docs/16_audit/` files are tracked, this ledger among them | `git ls-tree -r --name-only <base> docs/16_audit` → 91 entries (90 besides the ledger) |
| the policy file's real path | `docs/16_audit/HERMES-POLICY-AUTH-BOUNDARIES-2026-08-03.md` |

`7180433e73d2` exists and is an ancestor of the pinned base.

## §5. Exact scope

Exactly two files change:

- `docs/16_audit/OPEN-FOLLOWUPS.md`: 3 insertions, 3 deletions (the header);
- `docs/16_audit/BBF-doc-drift-flip-18.md`: this brief.

No source, test, workflow, configuration, lockfile, or generated API file
changes. No default changes. No runtime behaviour changes.

## §6. Verification

- the ledger stays at 3,884 lines, trailing newline preserved, LF-only, no BOM;
- exactly three ledger lines differ from the base (7, 8, 9); every other line
  is byte-identical;
- all ten PR #194 pointer values are unchanged and resolve to their referenced
  FU headings;
- the edit is **surgical**: replacing the three new lines back with the three
  old ones reproduces the base blob byte-for-byte;
- `git diff --check` is clean; no file-mode regressions;
- the flip-rules gate passes in manifest mode: scope, numstat, SHA ancestry,
  content anchors, and preservation ranges — each anchor and each preservation
  range verified in its own invocation, because `--anchor` and `--preserve` are
  last-wins flags;
- the gate is proven **non-vacuous**: a wrong numstat, a wrong file set, a
  wrong anchor, a genuinely non-ancestor SHA, and a preservation range
  covering a changed line are each rejected, while a preservation range over
  unchanged lines passes;
- the commit-reference gate passes, and rejects a stale `path:NNN` and a
  non-existent file when unbackticked.

**No runtime test was executed for this change.** The change is three lines of
prose in a markdown file with no behavioural surface.

## §7. Explicit exclusions

- **The ledger's `2026-11-09` paragraph label.** The squash that landed the
  AppContainer backend is dated **2026-11-11** (`f57bfcc1`); the label is
  pre-existing ledger text at a different edit site (the FU-20 entry, well
  below this header). Correcting it is a separate correction with its own
  line-count consideration, and mixing the two would make this flip's measured
  scope ambiguous.
- **FU-20's lead status line and its `**Status:** OPEN` line.** The lead is
  accurate as it stands; the `OPEN` line is preserved history under a
  `RESOLVED` lead. flip-16 and flip-17 both recorded the same reasoning, and
  it still holds.
- **Decision B (the shipped-default flip).** Not requested here.
- **The companion policy file's own "untracked" self-description.**
  `docs/16_audit/HERMES-POLICY-AUTH-BOUNDARIES-2026-08-03.md` — the file the
  corrected header now points to — is tracked (added by squash `d3c5a18a`,
  2026-08-10), yet its persistence section still describes itself as
  "untracked, per the project's `docs/16_audit/` convention". That is the same
  stale convention, in a second file, at a second edit site. It is a separate
  correction and is not touched here. Note that the same policy file already
  records, in its own incident note, that this ledger "was tracked the whole
  time" — so the correction this flip makes was established by the project
  before the header was fixed.
- **The loose ledger mirror** under the host's `Downloads/` directory. It is a
  **copy**, not a checkout, and it has no commit to be correct against;
  replacing it is a file-copy operation outside this repository, not part of
  this flip. The host's copy has been refreshed to this flip's ledger blob.
- **The container's ledger copies.** They live under
  `/a0/usr/workdir/*/docs/16_audit/` and `/a0/usr/projects/claude_auditor/` —
  the container's project directory holds none, and only its `apps/desktop/src`
  subtree is bind-mounted to this host. They are outside this repository, they
  are not at this flip's ledger blob, and they were not touched.
- **The two sibling worktrees** `cc-audit` and `cc-phase8`. Each worktree's
  **committed** ledger blob corresponds to its own HEAD — they are correct
  against their own commits — so overwriting their ledgers would dirty a
  worktree against its own commit. They are not mirrors and must not be
  refreshed. (`cc-audit`'s on-disk copy additionally differs from its own blob
  by CRLF line endings only, because that worktree predates the repository's
  LF policy; `git status` reports no change for the file there.)

## §8. Honest limitations

- **No runtime test was executed for this flip.** The change is three lines of
  prose with no behavioural surface; the measurements in §4 are static reads of
  the base tree.
- **This flip does not re-verify anything about FU-20's behaviour.** It
  corrects a provenance claim about the ledger file itself. FU-20's and
  FU-22's own behaviours were verified by their own BBFs.
- **This flip does not claim the ledger is free of further stale claims.** It
  corrects the one provenance claim it measured. A later state change could
  make another claim stale, exactly as PR #84 made this one stale.
- **The header's date is the date the file became tracked**, which is the
  commit's own date. A reader who wants the reason should look at PR #84's
  diff; this flip records that the file was added there, not why.

## §9. Maintenance-cost estimate

Three lines in the ledger's preamble, and this brief. Because the edit is
line-count neutral, no pointer recomputation is needed now. The next flip that
adds or removes lines **above** the pointer region must re-verify the pointer
values against the would-land tree, as PR #194's rebase did.
