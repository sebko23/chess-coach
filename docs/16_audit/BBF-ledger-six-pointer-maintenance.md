# BBF-ledger-six-pointer-maintenance — pointer-only maintenance of six stale `Original entry` ranges

**Date:** 2026-10-28
**Type:** documentation maintenance (pointer values only)
**Authorized by:** the ledger six-pointer maintenance directive (2026-10-28), with the
continuation checkpoint of the same date fixing the range convention and the target set.
**Base commit:** `5a5a67603fb4175d9564962fa96f796bf2d86042`

## §1. What this BBF does

Six `**Original entry:** lines N-M` pointers in the `## Resolved` section of
`docs/16_audit/OPEN-FOLLOWUPS.md` cited line ranges that no longer match the entries they
point at. Later BBFs inserted content above those entries, so every referenced range drifted
forward. This BBF updates the six range values and nothing else.

It changes no finding's status, title, body, severity, evidence, hash, date, citation, or
resolution prose. It touches no code, test, workflow, configuration, or dependency.

## §2. The range convention: Rule B

**Rule B: the referenced entry's heading line through its last non-blank line.** Trailing blank
lines and `---` separator lines are excluded.

Rule B was chosen because it matches the most recent merged precedent for exactly this edit:
PR #185 (`c5b2f729`, `BBF-doc-drift-flip-13`) corrected FU-38's own pointer by writing
`lines 2782-2911`, which is the heading through the last non-blank line of the FU-38 entry at
that tree.

The historical convention in this ledger is **not** uniform, and this BBF does not normalize it.
Reconstructing the six original values at their authoring trees shows three different rules in
use (`heading..pre-next`, `heading..last-content`, and `heading..before-separator`), which is
why the pointers drifted by differing amounts. Rule B is adopted going forward for this
maintenance and is recorded here so the next reader knows which convention produced these six
values.

`docs/16_audit/BBF-FLIP-PROCESS-RULES.md` §1.3 requires that a cited range "encompasses every
item named in the prose rather than merely resolving to some text". Rule B satisfies that: the
cited range equals the referenced entry's full extent, so every named item is inside it.

## §3. The six pointers: before and after

All ranges are computed against the post-edit tree. The edit replaces values inside existing
lines, so the file's line count is unchanged (3674 lines before and after) and no referenced
entry shifts. This was verified, not assumed.

| Finding | Stable anchor (`## FU-NN` heading) | Before | After | Entry extent (Rule B) |
|---|---|---:|---:|---:|
| FU-24 | `## FU-24 — Stale doc pointers found during PR #102 leaf review …` | 1790-1819 | **2021-2051** | 2021-2051 |
| FU-28 | `## FU-28 — Backend test-enforcement gap: CI runs 16 of 58 test files` | 1902-1942 | **2136-2183** | 2136-2183 |
| FU-31 | `## FU-31 — test_pdf_ingest_security.py::test_route_is_wired_to_smoke_yml …` | 1989-2031 | **2270-2320** | 2270-2320 |
| FU-32 | `## FU-32 — test_repertoire_recommendations_polyglot.py::test_book_path_is_directory …` | 2032-2078 | **2322-2375** | 2322-2375 |
| FU-33 | `## FU-33 — Stale smoke.yml:178-192 reference in PR #110 commit body …` | 2079-2117 | **2377-2425** | 2377-2425 |
| FU-34 | `## FU-34 — pnpm audit failure on main: GHSA-cp6q-959q-f8rh …` | 2123-2167 | **2428-2480** | 2428-2480 |

## §4. Why exactly these six

The candidate set was enumerated against the tree immediately before PR #185 (`7848c51e`),
which is where the directive says the six were observed. Recomputing every pointer's extent at
that tree yields exactly six stale pointers — FU-24, FU-28, FU-31, FU-32, FU-33, FU-34. PR #185
corrected FU-38's own pointer in the same pass, which is why FU-38 is not among the six.

That is the directive's stop condition: the tree contained exactly six independently stale
candidates, so the edit was not broadened.

## §5. Pointers deliberately NOT changed

Three other pointers are stale by the same raw recomputation. They are left untouched, and this
BBF does not normalize them:

| Finding | Cited | Rule-B extent at the post-edit tree | Why excluded |
|---|---:|---:|---|
| FU-22 | 1820-1918 | 1820-1919 | Outside the demonstrated pre-PR-#185 six; changed by the later PR #187 merge; explicitly protected by the directive. |
| FU-35 | 2479-2582 | 2482-2586 | Outside the demonstrated six; changed by the later BBF-FU-35-pyinstaller-collect-all merge; explicitly protected. |
| FU-38 | 2782-2919 | 2787-2925 | Corrected by PR #185 in the same pass that left the other six; explicitly protected. |

Their cited values are unchanged by this BBF — verified byte-for-byte against the base.

## §6. Verification

1. **Staleness proven before the edit.** Each of the six was recomputed against the base tree
   and shown to differ from its cited value, with the exact old range captured.
2. **Post-edit recomputation.** Rule B recomputed on the post-edit tree reproduces each of the
   six written values exactly, and the file's line count is unchanged, so no range became stale
   during the edit.
3. **Containment.** For each of the six, the cited range starts at or before the entry heading
   and ends at or after the entry's last non-blank line — the cited range contains the complete
   referenced entry, which is what `BBF-FLIP-PROCESS-RULES.md` §1.3 requires.
4. **Semantic-normalized diff.** With every `lines N-M` value replaced by a `<RANGE>`
   placeholder, the base file and the edited file are **identical** line-for-line (3674 lines
   each). Exactly six lines differ in the raw diff, and every one of them is an
   `**Original entry:**` pointer line whose only change is the range value.
5. **No newly stale pointer.** A full re-enumeration of all nine pointers on the post-edit tree
   finds no pointer newly out of range. The six targets are Rule-B exact; the three protected
   pointers are unchanged.
6. **Scope.** The changed-file set is exactly the ledger and this brief. No source, test,
   workflow, configuration, or dependency file changed.

## §7. Host anomaly (disclosed, no scope impact)

On this Windows host, `scripts/dev/verify_bbb_flip_rules.py` is intermittently unreadable:
`stat`, `head`, and `grep` sometimes report it missing while `os.listdir`/`os.stat`/`open()` and
the script's own execution succeed. The path is present in `git ls-tree HEAD`, the blob
(`ef65039c…`) is intact, the repository is clean, and `HEAD` equals `origin/main`. This is a host
filesystem/AV artifact, not repository damage. The tracked script was **not** modified, restored,
replaced, or committed; the intact git blob was used as the authority for reading and running the
gate.

## §8. Explicitly out of scope

- No finding status, title, body, severity, evidence, hash, date, citation, or resolution prose
  was changed.
- No pointer outside the demonstrated six was repaired.
- No code, test, workflow, configuration, dependency, or unrelated document was touched.
- The `chess_coach.gold` package-declaration question and the FU-22 B2 Windows-enforcement work
  are separate, separately-approved items and are not touched here.
