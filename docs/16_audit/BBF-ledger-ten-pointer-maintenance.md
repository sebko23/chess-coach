# BBF-ledger-ten-pointer-maintenance — pointer-only maintenance of ten stale `Original entry` ranges

**Date:** 2026-11-05
**Type:** documentation maintenance (pointer values only)
**Authorized by:** the queue directive of 2026-11-05 ("go 1" — the combined pointer-maintenance item), superseding and extending the 2026-10-28 ledger six-pointer maintenance directive.
**Base commit:** `96ced377c97342def3531258f2a0945007b1c865`

## §1. What this BBF does

Every `**Original entry:** lines N-M` pointer in the `## Resolved` section of
`docs/16_audit/OPEN-FOLLOWUPS.md` had drifted away from the entry it points at. Later BBFs
inserted content above those entries, so the referenced ranges moved forward and the
pointers kept citing the old positions.

This BBF updates the ten range values and nothing else.

It changes no finding's status, title, body, severity, evidence, hash, date, citation, or
resolution prose. It touches no code, test, workflow, configuration, or dependency.

## §2. The range convention: Rule B, measured

**Rule B: the referenced entry's heading line through its last non-blank line.** A trailing
`---` separator line counts as the last non-blank line when it is the entry's final line.

This BBF **measured** the convention instead of inheriting it, because the prose of the
previous pointer-maintenance brief (`docs/16_audit/BBF-ledger-six-pointer-maintenance.md` §2)
and that brief's own published tables disagree.

Two candidate readings of "heading through the last non-blank line" were tested against the
published values of the previous maintenance BBF at its post-edit tree `e9eed1b1`:

| Reading | `## FU-NN` heading → last non-blank line, `---` separator **excluded** | `## FU-NN` heading → last non-blank line, `---` separator **included** |
|---|---:|---:|
| Previous BBF §3 "After" column (six targets) | 5/6 reproduced | **6/6 reproduced** |
| Previous BBF §5 protected extents (three targets) | 1/3 reproduced | **3/3 reproduced** |
| **Total** | **6/9** | **9/9** |

The published values are what landed on `main`, so they are the repository's operative
convention. Rule B therefore means the separator-inclusive reading, and that is the reading
this BBF uses for all ten replacement values.

**Disclosed inconsistency.** `BBF-ledger-six-pointer-maintenance.md` §2 states that trailing
blank lines and `---` separator lines are excluded. Its own §3 and §5 tables were produced
by the separator-inclusive reading. The prose and the tables of that brief disagree; the
tables were followed, and this brief records the measured rule so the next reader does not
re-derive it. The previous brief is **not** modified by this BBF — it is a historical
record of a shipped change.

A wider sweep over the ledger's whole history confirms the repository has never used one
uniform rule. Of the pointer values written by commits **before this change** — seventeen
in total — five match **both** readings, two match only the separator-exclusive reading,
two match only the separator-inclusive reading, and eight match neither. Counting each
value under the separator-exclusive reading first — so that the five dual matches are
attributed to it — yields seven exclusive, two inclusive-only, and eight matching neither.

The eight values that match neither predate any stated convention. Five of them (FU-24,
FU-28, FU-31, FU-32, FU-34) were the drift the 2026-10-28 directive set out to fix, and
that BBF repointed them; the other three (FU-22, FU-35, FU-38) were the ones it
explicitly protected.

This BBF writes ten more pointer values, all separator-inclusive, so the totals in this
paragraph describe the ledger's history **as it stood at the base commit** and are stated
here as such rather than as a running count.

The two readings are therefore not competing global conventions — the ledger has no single
convention. What the measurement establishes is narrower and sufficient: the immediately
preceding maintenance of this exact pointer class (the 2026-10-28 BBF) produced
separator-inclusive values, its nine published extents reproduce 9/9 under that reading,
and it applied the same reading to the three pointers it then protected (FU-22 at
1820-1919, FU-35 at 2482-2586, FU-38 at 2787-2925 — FU-35 and FU-38 each differ from
their separator-exclusive extent by two lines, while FU-22's entry has no trailing
separator and so does not differ). This BBF is the direct successor of that maintenance,
so it continues with the separator-inclusive reading for continuity of the maintained set.

## §3. The ten pointers: before and after

All ranges are computed against the post-edit tree. The edit replaces values inside
existing lines, so the file's line count is unchanged and no referenced entry shifts. This
was verified, not assumed.

Per `docs/16_audit/BBF-FLIP-PROCESS-RULES.md` §1.1, the trailing-newline behavior is
stated explicitly: the ledger ends with a trailing newline, so it measures **3871 lines** by
`wc -l` and yields **3872 newline-separated fields** when split, the last being the empty
field after that trailing newline. Both counts are identical before and after the edit.

| Finding | Stable anchor (`## FU-NN` heading) | Before | After | Rule B extent |
|---|---|---:|---:|---:|
| FU-11 | `## FU-11 — Polyglot opening-book persistent support (β, Phase 2 trigger)` | 795-856 | **795-858** | 795-858 |
| FU-24 | `## FU-24 — Stale doc pointers found during PR #102 leaf review …` | 2021-2051 | **2110-2140** | 2110-2140 |
| FU-28 | `## FU-28 — Backend test-enforcement gap: CI runs 16 of 58 test files` | 2136-2183 | **2225-2272** | 2225-2272 |
| FU-31 | `## FU-31 — test_pdf_ingest_security.py::test_route_is_wired_to_smoke_yml …` | 2270-2320 | **2359-2409** | 2359-2409 |
| FU-32 | `## FU-32 — test_repertoire_recommendations_polyglot.py::test_book_path_is_directory …` | 2322-2375 | **2411-2464** | 2411-2464 |
| FU-33 | `## FU-33 — Stale workflow-file reference in PR #110 commit body` (heading quoted with the file name elided; the verbatim heading names a workflow file and a line range) | 2377-2425 | **2466-2514** | 2466-2514 |
| FU-34 | `## FU-34 — pnpm audit failure on main: GHSA-cp6q-959q-f8rh …` | 2428-2480 | **2517-2569** | 2517-2569 |
| FU-35 | `## FU-35 — chess_coach implicit namespace package blocks clean PyInstaller packaging` | 2479-2582 | **2571-2675** | 2571-2675 |
| FU-38 | `## FU-38 — 29 pre-existing historical gitleaks findings (allowlist …)` | 2782-2919 | **2876-3014** | 2876-3014 |
| FU-22 | `## FU-22 — A-F11 property 4 (2GB memory cap) has no implementation …` | 1820-1918 | **1909-2008** | 1909-2008 |

Each replacement range starts at the referenced entry's heading line and ends at that
entry's last non-blank line, so it contains the complete referenced entry. This satisfies
`docs/16_audit/BBF-FLIP-PROCESS-RULES.md` §1.3: the cited range encompasses every item the
surrounding prose names, rather than merely resolving to some text.

## §4. Why exactly these ten

The candidate set was enumerated against the current base tree `96ced377` by recomputing
every pointer's Rule B extent and comparing it to the pointer's cited value. At that tree
all ten pointers are stale and no pointer is exact, so the edit was not broadened beyond
the complete stale set — there is nothing left excluded for being correct.

The drift is uniform in cause: four merges since the previous pointer maintenance
(`a314107f`, `ed803d6d`, `df3ed9bf`, `96ced377`) inserted content above the referenced
entries. The ledger grew from 3673 to 3871 lines across that span.

Three of the ten — FU-22, FU-35, FU-38 — were explicitly **protected** by the 2026-10-28
directive, which said not to edit them. That protection is superseded by the 2026-11-05
authorization, which names the protected pointer maintenance as an approved item. Their
prose, status, and evidence are untouched; only the range values that point at their own
entries change, exactly as for the other seven.

FU-11's own pointer is included because the FU-11 merge wrote it against a tree that then
changed again, and the same `---`-separator reading that the other nine use puts its entry
at 795-858.

## §5. Pointers deliberately NOT changed

None. Every `**Original entry:**` pointer in the ledger is in the table in §3, and each is
edited to its Rule B extent. The ledger contains ten such pointers and no others.

## §6. Verification

1. **Convention measured, not assumed.** Two readings of Rule B were tested against the
   previous BBF's nine published values at its post-edit tree. The separator-inclusive
   reading reproduces 9/9; the separator-exclusive reading reproduces 6/9. The
   separator-inclusive reading is used. See §2.
2. **Staleness proven before the edit.** Each of the ten was recomputed against the base
   tree and shown to differ from its cited value, with the exact old range captured.
3. **Post-edit recomputation.** Rule B recomputed on the post-edit tree reproduces each of
   the ten written values exactly, and the file's line count is unchanged (3872 before and
   after), so no range became stale during the edit.
4. **Semantic-normalized diff.** With every `lines N-M` value replaced by a `<RANGE>`
   placeholder, the base file and the edited file are **identical line-for-line** (3872
   lines each). Exactly ten lines differ in the raw diff, and every one of them is an
   `**Original entry:**` pointer line whose only change is the range value. The ledger's
   numstat is 10 insertions and 10 deletions, all in that one file.
5. **Containment.** For each of the ten, the cited range starts at the entry heading and
   ends at the entry's last non-blank line — it contains the complete referenced entry.
6. **No newly stale pointer.** A full re-enumeration of all ten pointers on the post-edit
   tree finds every one Rule B exact. None is out of range.
7. **Scope.** The changed-file set is exactly the ledger and this brief. No source, test,
   workflow, configuration, or dependency file changed.

## §7. Explicitly out of scope

- No finding status, title, body, severity, evidence, hash, date, citation, or resolution
  prose was changed.
- No pointer outside the ten demonstrated stale pointers was repaired — there are none.
- No code, test, workflow, configuration, dependency, or unrelated document was touched.
- `docs/16_audit/BBF-ledger-six-pointer-maintenance.md` was **not** modified. Its
  prose/table inconsistency is disclosed here rather than corrected there, because that
  brief is the historical record of a shipped change and rewriting it would be an
  unrelated edit to a closed BBF's evidence.
- The `chess_coach.gold` package-declaration decision, FU-22 B2 Windows enforcement, and
  the Windows AppContainer network isolation are separate, separately-approved items and
  are not touched here.
