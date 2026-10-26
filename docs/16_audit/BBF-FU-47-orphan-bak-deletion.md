# BBF-FU-47 — delete the two orphan `.bak` files

**Date:** 2026-10-26
**Branch:** `bbf-fu-47-orphan-bak-deletion`
**Base:** `03c512f5fc201165d8ed5a6536a03a2bc446f108` (`main`, the FU-46 merge)

## Objective

Delete the two orphan `.bak` files that FU-46 deliberately left in the tree,
and remove the `.gitattributes` exact-path freezes that existed only to
protect them.

| Path | Size |
|---|---:|
| `apps/desktop/src/components/panels/coach/CoachPanel.tsx.bak_1780860511` | 16,855 B |
| `services/chess_coach/gateway/routes/repertoire_recommendations.py.bak` | 5,999 B |

## Why these files are safe to delete

### They were never used

Both files arrived together in a single commit and were never touched again:

| File | Added | Commits touching it | Last changed |
|---|---|---:|---|
| `CoachPanel.tsx.bak_1780860511` | 2026-06-13 | **1** | 2026-06-13 |
| `repertoire_recommendations.py.bak` | 2026-06-13 | **1** | 2026-06-13 |

The commit that added them is a 2026-06-13 commit titled "backup: pre-player-atom state snapshot before shared atom migration" — and they have been
byte-identical ever since. Their blobs are unchanged from that commit through
the current `main`.

That commit is not reachable from `main` in this repository's history (the
clone's boundary sits at `cd43906c`), so it is named here by its date and
subject rather than by object id.

Their live siblings have been actively maintained since:

| Live file | Commits |
|---|---:|
| `apps/desktop/src/components/panels/coach/CoachPanel.tsx` | 3 |
| `services/chess_coach/gateway/routes/repertoire_recommendations.py` | 11 |

### Nothing references them

- `git grep` over every tracked file finds **no** import, require, include,
  build manifest (`*.spec`, `pyproject.toml`), CI workflow, or script
  reference to either path.
- The frontend imports `./CoachPanel` — the live sibling — in
  `apps/desktop/src/routes/coach.tsx` and
  `apps/desktop/src/components/panels/coach/CoachPanel.test.tsx`. Neither
  references the `.bak` file.
- The UTF-8 mojibake guard never scanned either file. Its `shouldScan()`
  applies two filters in order, and the **suffix filter fires first**:
  `SKIP_SUFFIXES.some((s) => rel.includes(s))`, with `SKIP_SUFFIXES` holding
  `.bak` and `.bak.`. That is a *substring* test, and
  `CoachPanel.tsx.bak_1780860511` contains `.bak` — so the file is excluded
  by the suffix list. Its extension filter
  `/\.(ts|tsx|js|jsx|mjs|cjs|json|md|html|css|scss)$/` would also have
  excluded it (the name ends in `_1780860511`, not in a scanned extension),
  but that check is never reached.

### Almost all their content already exists elsewhere in git history

The `.bak` files are not strict subsets of their live siblings — by
`difflib.SequenceMatcher` opcode counts over raw lines, the `.tsx` one
matches 428 of its 533 lines against the live file and the `.py` one matches
122 of 189 — so "the live file is newer" is not the argument. (That figure is
a raw-line diff count; other comparison methods, such as comparing distinct
non-blank lines, give different numbers.)

The argument is history, and it is almost complete. The corpus is every blob
reachable from a full bare clone of the upstream repository —
`git rev-list --objects --all` (597 commits, 1,843 reachable blobs) — with the
two `.bak` blobs themselves excluded from the corpus so the check cannot be
satisfied by the file being examined:

| File | Non-blank lines | Found elsewhere in history | Found nowhere else |
|---|---:|---:|---:|
| `CoachPanel.tsx.bak_1780860511` | 486 | **485 of 486** | **1** |
| `repertoire_recommendations.py.bak` | 160 | **160 of 160** | **0** |

The single exception is one comment line annotating the `debouncedFen!` argument in the `.tsx` file. That line
existed only in this snapshot; the live file was rewritten without it. It is a
comment, and the code it annotates — the `debouncedFen!` non-null assertion —
is present in the live sibling. So almost no content is lost.

That line is deliberately described rather than quoted: reproducing it
verbatim in this document would put it back into the corpus and make the
measurement self-referential again.

Deletion is still fully reversible: both blobs remain permanently reachable
in the object store, and `git show cd43906c:<path>` returns bytes identical to
the base tree (16,855 B and 5,999 B).

## Changes

### 1. Delete the two files

`git rm` both paths. 532 and 188 lines removed respectively.

### 2. Remove the now-dead exact-path freezes from `.gitattributes`

FU-46 pinned the two paths with exact-path `-text` rules so their bytes
would stay frozen while they were awaiting deletion. With the files gone,
those rules match nothing.

They are removed rather than left in place, because a retained rule would
silently freeze a **future** file added at either path without review —
exactly the failure mode FU-46's own comment warned against when it chose
exact paths over a `*.bak` glob.

The policy shrinks from 39 active rules to **37**:

| Property | Before (FU-46) | After (FU-47) |
|---|---:|---:|
| Active rules | 39 | **37** |
| — binary | 6 | 6 |
| — glob text (`text eol=lf`) | 23 | 23 |
| — dotfile/extensionless text | 8 | 8 |
| — exact-path `-text` freezes | 2 | **0** |
| File size | 3,030 B | **2,122 B** |
| Lines | 76 | **61** |
| SHA-256 | `c37388d0…` | `92d8535edfef7e32370d77e2cc21e6a8e435d6f6c6f6339771b8cc51aca78795` |

The binary rules remain **last**, and the header comment's rationale for
that order is unchanged (FU-46's review established that `binary` is
`-text -diff`, so a *later* binary rule is what clears `text`).

## Verification

### Attribute coverage is still complete

`git check-attr -z text eol binary --stdin` over all **869** tracked paths
of the head tree:

| Result | Count |
|---|---:|
| Parsed | 869 |
| `text: unspecified` | **0** |
| `text: set` (with `eol: lf`) | 778 |
| `text: unset` | 91 |
| `binary: set` | 91 |

The 91 `text: unset` paths are exactly the 91 binary assets. No path is left
without an explicit attribute.

### Nothing else moved

- 0 of the 91 binary assets changed.
- 0 of the 869 remaining text blobs changed — the deletion touches no
  surviving file's bytes.
- The live siblings are untouched: `CoachPanel.tsx` (17,906 B) and
  `repertoire_recommendations.py` (18,896 B) keep their blobs exactly.

### Gates

Run with the CI's exact commands:

| Gate | Result |
|---|---|
| `pytest` (CI coverage invocation, `--cov-fail-under=55`) | exit 0 |
| `ruff check libs services apps/cli tests scripts` | exit 0 |
| `mypy libs services apps/cli --no-incremental --platform linux` | exit 0 |
| `gen-api --check` | exit 0 |
| `git diff --check` | silent |

### Ledger

One pure insertion into `docs/16_audit/OPEN-FOLLOWUPS.md`: the FU-47 entry,
placed before `## Resolved`. Zero deletions, zero replacements, every base
line preserved in order.

## Deliberately out of scope

- **The live siblings.** `CoachPanel.tsx` and
  `repertoire_recommendations.py` are not modified in any way.
- **The UTF-8 mojibake guard's `SKIP_SUFFIXES` list.** It still contains
  `.bak` and `.bak.`. That is a general safety property for future backup
  files, independent of whether any exist today.
- **`.gitignore`.** It already excludes `.a0proj/memory/*.bak`; that rule is
  unrelated to these two tracked files.
- **Any other `.bak` path.** These two were the only tracked `.bak` files;
  the other `.bak` mentions in the tree are documentation prose about
  unrelated paths (`/a0/plugins/…/default_config.yaml.bak.before-…`,
  `chess_coach.db.bak_78kb`).

## Relationship to FU-46

FU-46 added the line-ending policy and deliberately left the two orphans in
the tree, frozen rather than normalized, with their deletion named as a
separate cleanup BBF. This BBF is that cleanup.

FU-46's own measurements remain valid as statements about the tree at its
own base and head. The figures that describe the **current** tree change:
the tracked-path count drops from 870 to 869, and the frozen orphan no
longer exists. FU-46's brief is not rewritten here — its measurements are
point-in-time facts about its own commits — but this brief records the
current state.

## Provenance

The deletion, the policy edit, and every measurement in this brief were
produced on the authenticated host against the merged FU-46 tree at
`03c512f5fc201165d8ed5a6536a03a2bc446f108`. The safety analysis
(line-overlap, history reachability, reference sweep, extension-filter
behaviour) was run against git object bytes, not working-tree bytes.
