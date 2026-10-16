# BBF-FU-29-mypy-burndown — Stage 1 mypy easy-sub-burndown (169 → 135 errors)

**Sprint intent:** Execute Stage 1 of the FU-29 ratchet
(per `BBF-FU-29-scoping-brief.md` §2, shipped at
`e2da99c7`) for the **mypy** tool — but **only the
easy sub-scope** (16 `unused-ignore` deletes + 18
`import-not-found` config adds). The remaining 135
errors (50 `no-untyped-def`, 32 `type-arg`, 20
`no-any-return`, plus 33 misc) require real semantic
work and are deferred to a follow-up BBF.

**Status:** Code+config BBF. 11 files modified.

## §1. The 169 errors (before fix)

Per the 2026-10-16 re-measurement (per
`BBF-FU-29-status-check.md`, shipped at `8e4e62e3`):

| Count | Code | Description |
|---|---|---|
| 50 | `no-untyped-def` | Function is missing a type annotation |
| 32 | `type-arg` | Missing type arguments for generic type |
| 20 | `no-any-return` | Returning Any from function declared to return X |
| 18 | `import-not-found` | Cannot find implementation or library stub |
| 16 | `unused-ignore` | Unused `# type: ignore` comment |
| 9 | `union-attr` | Item of union has no attribute |
| 4 | `arg-type` | Argument type mismatch |
| 4 | `attr-defined` | Type has no attribute |
| 3 | `no-untyped-call` | Call to untyped function in typed context |
| 3 | `assignment` | Incompatible assignment |
| 3 | `misc` | Other (mostly list-comprehension type mismatch) |
| 3 | `index` | Value of type "X \| None" is not indexable |
| 1 each | `var-annotated`, `return-value`, `name-defined`, `operator` | 1 of each |
| **169** | **total** | |

## §2. The 34 easy fixes (this BBF)

### 16 `unused-ignore` deletes (mechanical)

The `# type: ignore[import-not-found]`, `# type: ignore[attr-defined]`,
and `# type: ignore[assignment]` comments on 16 lines across 10 files
are stale — the strict-mode mypy settings no longer trigger them
(because the code's now correctly typed). Just delete them.

| File | Line(s) | Code |
|---|---|---|
| `libs/chess_coach/datasets/narrative_gold.py` | 186 | `unused-ignore` (import-not-found) |
| `libs/chess_coach/datasets/l2_gold.py` | 175 | `unused-ignore` (import-not-found) |
| `libs/chess_coach/storage/migrate.py` | 58 | `unused-ignore` (attr-defined) |
| `libs/chess_coach/protocol_types/narration.py` | 9 | `unused-ignore` (assignment) |
| `services/chess_coach/narration/validator.py` | 13 | `unused-ignore` (assignment) |
| `services/chess_coach/gateway/routes/engines.py` | 27 | `unused-ignore` (attr-defined) |
| `services/chess_coach/gateway/routes/analysis.py` | 25 | `unused-ignore` (attr-defined) |
| `services/chess_coach/gateway/routes/kb.py` | 88 | `unused-ignore` (attr-defined) |
| `services/chess_coach/gateway/app.py` | 122, 169, 184, 218, 247, 267, 299 | `unused-ignore` (attr-defined) × 7 |
| `services/chess_coach/gateway/__main__.py` | 114 | `unused-ignore` (attr-defined) |

### 18 `import-not-found` config adds (1 line of pyproject.toml)

The 4 modules below have no type stubs (or the stubs
are not in mypy_path). Add a `[tool.mypy.overrides]`
block to tell mypy to treat them as untyped (Any):

| Module | Occurrences | Files |
|---|---|---|
| `aiosqlite` | 14 | gateway routes (route_guard, training_planner, training, repertoire_recommendations, repertoire, profile, players, pgn_import, lichess_import, game_routes, eval_graph, blunder_routes, backfill_analyses, pdf_ingest, narration) |
| `keyring` | 1 | `services/chess_coach/keychain/__init__.py` |
| `sentence_transformers` | 1 | `services/chess_coach/kb/embedder.py` |
| `sklearn.metrics.pairwise` | 1 | `services/chess_coach/kb/embedder.py` |

The fix (in `pyproject.toml`):

```toml
[[tool.mypy.overrides]]
module = ["aiosqlite", "keyring", "sentence_transformers", "sklearn.metrics.pairwise"]
ignore_missing_imports = true
```

This is the standard mypy pattern for libraries
without type annotations. It's the same pattern
already used for `chess.*` in the existing
`[tool.mypy.overrides]` block.

## §3. The 135 errors remaining (deferred)

The remaining 135 errors are real type errors that
require semantic work:

| Count | Code | Why deferred |
|---|---|---|
| 50 | `no-untyped-def` | Adding type annotations to 50 functions is real work; estimates 1-2 hrs |
| 32 | `type-arg` | Adding `tuple[X, Y]` instead of bare `tuple` is mechanical but tedious; ~30 min |
| 20 | `no-any-return` | Refining return types to avoid Any; ~1 hr |
| 9 | `union-attr` | Adding None-checks; ~30 min |
| 4 each | `arg-type`, `attr-defined` | Type refinement; ~30 min |
| 3 each | `no-untyped-call`, `assignment`, `misc`, `index` | Mixed; ~1 hr |
| 1 each | `var-annotated`, `return-value`, `name-defined`, `operator` | Small; ~15 min |
| **135** | **total** | **~5-7 hrs of focused work** |

**The full mypy burn-down is a multi-BBF effort.**
The brief's §3 burn-down order says "mypy last (heaviest
— 154 errors, semantic, strict = true is aspirational)";
the re-measurement confirms this (169 errors, even more
since 2026-08-25).

**Recommended follow-up chain:**

- **`go FU-29-mypy-type-arg`** — Stage 1 mypy
  sub-burndown, sub-task A: fix the 32 `type-arg`
  errors (mechanical: add `tuple[X, Y]`, `dict[K, V]`,
  `list[X]`, etc.). ~30 min, 1 PR.
- **`go FU-29-mypy-no-untyped-def`** — Stage 1 mypy
  sub-burndown, sub-task B: fix the 50 `no-untyped-def`
  errors (real semantic work). ~1-2 hrs, 1-2 PRs.
- **`go FU-29-mypy-no-any-return`** — Stage 1 mypy
  sub-burndown, sub-task C: fix the 20 `no-any-return`
  errors (refine return types). ~1 hr, 1 PR.
- **`go FU-29-mypy-misc`** — Stage 1 mypy sub-burndown,
  sub-task D: fix the remaining 33 errors (union-attr,
  arg-type, attr-defined, etc.). ~2 hrs, 1-2 PRs.
- **`go FU-29-mypy-wire-ci`** — Stage 3 mypy
  wire-to-CI (after all sub-tasks land).

**Order:** type-arg (cheapest, mechanical) → misc (real
work) → no-untyped-def (real work) → no-any-return (real
work) → wire to CI.

## §4. The verification (live, this session)

```
$ mypy libs services apps/cli --no-incremental
Found 169 errors in 38 files (checked 86 source files)
```

(Before fix.)

```
$ mypy libs services apps/cli --no-incremental
Found 135 errors in 30 files (checked 86 source files)
```

(After fix. **-34 errors, -8 files affected.**)

## §5. The CRLF footgun (caught and reverted)

The first attempt to apply the 16 `unused-ignore` deletes
introduced CRLF line endings in 4 files that have LF in
HEAD (`libs/chess_coach/datasets/l2_gold.py`,
`libs/chess_coach/storage/migrate.py`,
`services/chess_coach/narration/validator.py`,
`services/chess_coach/gateway/routes/kb.py`).

The first `git diff --stat` showed 644-line churn on
`l2_gold.py` (322 lines inserted, 322 deleted) — the
classic line-ending-churn signature. The CRLF-on-disk
was converted back to LF to match HEAD, and the fix
was re-applied in LF form. The final diff is the
expected 11 files, +29/-16 (1-line changes per file
plus the pyproject.toml add).

**This is the same LF-preservation discipline as the
FU-40 amend, the BBF-FU-20-21-22-spikes amend, the
FU-22-impl B2 amend, and the FU-29-ruff-burndown
amend.** The fix uses bytes mode to preserve the
HEAD line endings.

## §6. Honest disclosures

1. **The mypy burn-down is incomplete.** 135 of 169
   errors remain. This BBF is the easy sub-scope;
   the real semantic work is in 4 follow-up BBFs
   (per §3).

2. **The 16 `unused-ignore` deletes are mechanical
   and have no semantic impact.** The code is
   correct; the `# type: ignore` comments are stale.

3. **The 18 `import-not-found` config adds use
   `ignore_missing_imports = true` which means
   mypy treats these modules as `Any`.** This is
   the standard mypy pattern for libraries without
   type annotations; it's the same pattern already
   used for `chess.*` in the existing
   `[tool.mypy.overrides]` block.

4. **`core.autocrlf=false` is the git config on this
   machine.** The CRLF issue was caused by a
   previous `read_file` + bytes-mode mismatch, not
   by git's autocrlf setting. The fix (convert
   CRLF on disk back to LF) is the same regardless.

5. **The 12/13 CI green on `98780986` (the
   FU-29-ruff-wire-ci ship) is preserved.** This
   BBF adds no CI changes; the existing
   `gateway boot (clean install)` job will run the
   unit tests, and the new `ruff lint` job will
   run `ruff check`. Neither will be affected by
   the mypy burn-down (mypy is not in CI yet).

6. **The full mypy burn-down is a multi-BBF effort.**
   Per the brief's §3 burn-down order, "mypy last
   (heaviest — 154 errors, semantic)." The
   re-measurement confirmed this is a 2-4 hr
   effort, even more now (169 errors, 5-7 hrs).
   The easy sub-scope (this BBF) is 20% of the
   total; the remaining 80% is the 4 sub-tasks
   listed in §3.

7. **No new tests added.** The fix is mechanical
   (16 deletes + 1 config add); existing tests
   cover the affected code paths.

## §7. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-29 entry
  (the original ledger entry; this BBF is the
  Stage 1 mypy easy-sub-burndown).
- `docs/16_audit/BBF-FU-29-scoping-brief.md`
  (the ratchet-strategy brief, shipped at
  `e2da99c7`).
- `docs/16_audit/BBF-FU-29-status-check.md`
  (the re-measurement brief, shipped at
  `8e4e62e3`; this BBF acts on its findings).
- `docs/16_audit/BBF-FU-29-ruff-burndown.md`
  (the Stage 1 ruff sub-burndown, shipped at
  `a27da3f9`).
- `docs/16_audit/BBF-FU-29-ruff-wire-ci.md`
  (the Stage 3 ruff wire-to-CI, shipped at
  `98780986`).
- `pyproject.toml` lines 159-161 (the existing
  `[[tool.mypy.overrides]]` block for `chess.*`,
  the precedent for the new override).

## §8. Final report format

This BBF ships 11 file changes:

- `pyproject.toml` (modified, +13/-0) — new
  `[[tool.mypy.overrides]]` block for 4 modules.
- 10 Python files (modified, 1 line each) —
  delete the 16 stale `# type: ignore` comments.

**Total: 11 files, +29/-16.**

(One BBF brief is also new: this file.)
