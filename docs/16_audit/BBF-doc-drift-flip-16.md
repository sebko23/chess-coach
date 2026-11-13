# BBF-doc-drift-flip-16 — close the FU-30 and FU-35 stale mid-entry status declarations

**Status:** Draft for review
**Base:** `ab3aef09f23a2d076e69026ca8d36f68bb667341`

## §1. Why this flip exists

Two ledger entries carry a **mid-entry** `**Status:** OPEN` line while their own
entry lead already reads RESOLVED:

- **FU-30** — line 2369: `**Status:** OPEN — log only. Path fix deferred to a
  follow-up BBF that addresses the fixture factory design.`
- **FU-35** — line 2645: `**Status:** OPEN. Resolution shape:` followed by a
  six-step plan.

Both deferrals were **executed** after the lines were written, so both lines
assert open work that no longer exists, inside entries whose own leads say the
work is done. A reader scanning for `Status: OPEN` finds two live-looking open
items in entries that are closed.

This is the defect class flip-12's selection test missed: it skipped entries
whose lead was already RESOLVED, which is exactly where this class lives. FU-30's
fix (`1501f408`) was an ancestor of flip-12's base and was in scope but missed.
FU-35's packaging half (`bcb70d88`) landed after flip-12's base, so FU-35 was
legitimately open then and became newly-stale afterwards.

## §2. The scope-discharge test

`docs/16_audit/BBF-FLIP-PROCESS-RULES.md` §6 requires walking the entry's OWN
enumerated scope. Each deferral was measured against the base tree, not read
from the ledger.

**FU-30 — DISCHARGED.** The line defers a path fix for
`tests/perf/conftest.py`. Measured on the base tree:

| Claim | Measured |
|---|---|
| the hardcoded container path is gone | `tests/perf/conftest.py` contains **0** occurrences of `a0/usr/projects` |
| `snap_path` is derived, not hardcoded | `snap_path = os.path.join(qdrant_snapshot_dir, snap.name)`; `qdrant_snapshot_dir` is a fixture-injected parameter |
| the paths are env-driven | `CHESS_COACH_QDRANT_URL` and `CHESS_COACH_DATA_DIR` supply the defaults |
| the CI ignore is gone | `.github/workflows/smoke.yml` contains no `tests/perf` reference at all |

The fix shipped in squash `1501f408` (BBF-FU-30-perf-conftest-portable), an
ancestor of the base. Nothing remains to defer.

**FU-35 — DISCHARGED.** The line introduces a six-step resolution shape. Every
step was measured on the base tree:

| Step | Measured |
|---|---|
| 1. add `chess_coach/__init__.py` at the repo root | **present** (`chess_coach/__init__.py`, added by `99a355df`) |
| 2. make the package layout coexist | the spec's `pathex=[str(REPO_ROOT), *PACKAGE_ROOTS]` resolves both roots |
| 3. use `collect_all` instead of tree-level `datas=`, remove the runtime hook | the spec calls `collect_all(_pkg)` per subpackage; `runtime_hooks=[]`; the hook file `services/chess_coach/gateway/pyinstaller_rthook.py` is **absent from the tree** |
| 4. update the entry-point setup script | the spec's `datas=_C_DATAS` is built from `collect_all` results plus the root marker file — no source-tree bundling |

The structural half shipped in squash `99a355df` (2026-10-17) and the packaging
half in squash `bcb70d88` (BBF-FU-35-pyinstaller-collect-all). Both are
ancestors of the base. FU-35's own lead already records both halves and states
"FU-35 is closed in two parts".

**The entry's `datas=` mentions that remain in the spec are COMMENTS**, not live
arguments — the live `datas=` value is `_C_DATAS`, assembled from `collect_all`
results. The runtime-hook mentions are likewise comments; the live argument is
`runtime_hooks=[]`.

## §3. The replacement shape

Neither FU-30 nor FU-35 has a `**Status (clarified ...)**` block, so there is
no existing clarification to point at. This is the **flip-12 shape**: the stale
`**Status:**` line is replaced in place with a single RESOLVED line, and the
historical prose it introduced is preserved.

- **FU-30** — the stale block was 2 lines (`**Status:**` plus its continuation).
  It is replaced by 2 lines. The deferral prose above it, and the entry's
  `**Finding:**` body, are preserved byte-for-byte.
- **FU-35** — the stale `**Status:**` line was 1 line. It is replaced by 1 line.
  The six-step plan below it is preserved **byte-for-byte** as the historical
  record of what was planned; it is not collapsed, because collapsing it would
  delete evidence of the plan's origin.

No clarification block is introduced, so the unique-clarification rule holds.

## §4. Line-count neutrality is load-bearing here

PR #194 landed ten `**Original entry:** lines N-M` pointers in this same ledger
whose **values are line numbers**. Measured on the base tree, FU-30's stale
line at 2369 sits **above six** of the ten pointer targets, and FU-35's at
2645 sits above only **one** of them (a subset of FU-30's six). A net
line-count change in either place would shift those
pointer start lines and silently re-point them at the wrong FU entries — the
exact defect class PR #194 was merged to fix, and one no CI gate in this
repository can catch.

Both replacements are therefore line-count neutral **by construction**: 2 lines
for 2 lines, and 1 line for 1 line. The ledger stays at 3,884 lines and exactly
lines 2369, 2370 and 2645 differ from the base.

This was verified against the **synthetic merge tree**
(`git merge-tree --write-tree`), not merely the branch tree, because a
pointer's correctness is a property of the tree it lands in.

## §5. Verification

- The ledger stays at 3,884 lines, with its trailing newline preserved.
- Only lines 2369, 2370 and 2645 differ from the base; every other line is
  byte-identical.
- All ten PR #194 pointer values resolve to their entries' headings with
  correct Rule-B extents in the would-land tree.
- FU-30's `**Finding:**` body and FU-35's six-step plan are byte-identical to
  the base.
- `git diff --check` is clean.
- The flip-rules and commit-reference gates pass against the commit body and
  the PR body.

## §6. Explicit exclusions

- **FU-20.** Its later `**Status:** OPEN` line (1764) sits inside the entry's
  preserved `**Identified:** 2026-08-13` / `**The gap:**` historical body, under
  a lead that reads `RESOLVED for the named release scope (2026-10-30)` and
  explicitly scopes Windows as a separately-approved follow-up. The entry also
  carries an explicit `**Historical state (superseded 2026-10-29 by ...)**`
  block. It is historical content, not a contradiction to correct, and touching
  it would delete history.
- **FU-7, FU-9, FU-23, FU-27.** Each truthfully open, each excluded for a
  stated reason in §2's sibling analysis.
- **BBF-86.7 and PR #48.** The BBF-86 release-readiness audit and the
  external-review findings both claim BBF-86.7 is "✅ shipped", citing the
  commit PR #48 carries. That commit is **not** an ancestor of the base, and the
  corpus `version` field and the Dockerfile `BUILD_ARG` flags it would introduce
  are absent from the base tree. The claim is false and the scope is unlanded,
  but it is a separate BBF and a separate decision (PR #48's branch is far
  behind the base and would need a rebase), so it is **not** discharged here.
- No source, test, workflow, or configuration file is touched.

## §7. Honest limitations

- **No runtime test was executed for this flip.** The change is a three-line
  documentation edit with no behavioural surface, and the scope-discharge
  measurements in §2 are static reads of the base tree. FU-30's and FU-35's own
  behaviours were verified by their own BBFs; this flip does not re-verify them.
- **FU-35's step 4** ("update the entry-point setup script") is discharged by
  the absence of source-tree bundling in the spec's live `datas=` value rather
  than by a direct change to the console-script mapping; the mapping was not
  re-derived here, because the entry's own lead already records that half as
  shipped.
- **This flip does not claim the ledger is free of further stale
  declarations.** It closes the two instances found by a full per-entry sweep of
  every `**Status:**` line against its entry's live lead. A later state change
  could make another entry stale, exactly as it made these two.

## §8. Maintenance-cost estimate

Three lines in one ledger file. The next flip that edits above line 2372 must
re-verify the pointer values against the would-land tree, as PR #194's rebase
did.
