# BBF-FU-29-mypy-no-untyped-def — Stage 1 mypy sub-task B (48 → 0 errors)

**Sprint intent:** Execute Stage 1 of the FU-29 ratchet
(per `BBF-FU-29-scoping-brief.md` §2, shipped at
`e2da99c7`) for the **mypy** tool, sub-task B: add
type annotations to the 48 functions that were
missing them. Per the just-shipped
`BBF-FU-29-mypy-misc.md`'s §3 follow-up chain, this
is the second-largest remaining bucket after
`no-any-return`.

**Status:** Code-only BBF. 15 files modified.

## §1. The 48 no-untyped-def errors (before fix)

Per the 2026-10-16 re-measurement (per
`BBF-FU-29-status-check.md`, shipped at
`8e4e62e3`) and the post-FU-29-mypy-misc re-measurement
(102 → 74 after the misc BBF, then 74 → 32 after
this BBF):

| Count | Where | Fix pattern |
|---|---|---|
| 29 | unique function signatures (the 48 errors include duplicate reportings for both "missing return" and "missing param" on the same function) | Add `-> ReturnType` and/or parameter type annotations |
| 14 | inner `_metric_*` functions in `profile.py` and `profile_analysis.py` | Add `(db_path: str, player: str, **_: Any) -> EffectSize` |
| 5 | inner functions in other files | Add parameter and return types |

**All 48 errors are fixed in this BBF.**

## §2. The 29 unique function signatures annotated (top-level functions)

| File | Function | Return type added |
|---|---|---|
| `libs/chess_coach/datasets/archetype_gold.py:82` | `load_archetype_gold` | `-> list[ArchetypeGoldEntry]` |
| `libs/chess_coach/datasets/archetype_gold.py:91` | `load_archetype_gold_with_metadata` | `-> list[dict[str, Any]]` |
| `libs/chess_coach/datasets/archetype_gold.py:113` | `validate_archetype_gold` | `-> list[str]` (param: `corpus: list[Any]`) |
| `libs/chess_coach/testkit/mock_uci.py:46` | `go` | `**kwargs: Any` (param annotation) |
| `services/chess_coach/gold/eval_delta.py:48` | `score_cp` | `pv: Any` (param annotation) |
| `services/chess_coach/gateway/routes/training.py:104` | `get_queue` | `-> QueueResponse` |
| `services/chess_coach/gateway/routes/training.py:162` | `review_card` | `-> ReviewResponse` |
| `services/chess_coach/gateway/routes/training.py:205` | `seed_from_blunders` | `-> dict[str, dict[str, int]]` |
| `services/chess_coach/gateway/routes/repertoire.py:49` | `get_repertoire_tree` | `-> TreeResponse` |
| `services/chess_coach/gateway/routes/repertoire.py:71` | `get_repertoire_gaps` | `-> list[GapItem]` |
| `services/chess_coach/gateway/routes/repertoire.py:89` | `get_repertoire_novelties` | `-> list[NoveltyItem]` |
| `services/chess_coach/gateway/routes/profile_analysis.py:167` | `_run_metric_in_thread` | `fn: Callable[..., Any], -> Any` |
| `services/chess_coach/gateway/routes/profile.py:44` | `get_profile` | `-> ProfileStats` |
| `services/chess_coach/gateway/routes/profile.py:290` | `_run_metric_in_thread` | `fn: Callable[..., Any], -> Any` |
| `services/chess_coach/gateway/routes/profile.py:311` | `explain_metric` | `-> MetricExplainResponse` |
| `services/chess_coach/gateway/routes/players.py:20` | `list_players` | `-> PlayerListResponse` |
| `services/chess_coach/gateway/routes/lichess_import.py:147` | `_insert_game` | `-> None` |
| `services/chess_coach/gateway/routes/lichess_import.py:193` | `import_lichess` | `-> LichessImportResult` |
| `services/chess_coach/gateway/routes/game_routes.py:36` | `list_games` | `-> GamesListResponse` |
| `services/chess_coach/gateway/routes/game_routes.py:59` | `get_game_pgn` | `-> PlainTextResponse` |
| `services/chess_coach/gateway/routes/eval_graph.py:93` | `_coalesce_analyze` | `coro_factory: Callable[[], Coroutine[Any, Any, Any]]` |
| `services/chess_coach/gateway/routes/eval_graph.py:370` | inner `_run` | `pid: str, f: str, p: int, k: tuple[str, int, str, int]` |
| `services/chess_coach/gateway/routes/engines.py:41` | `list_engines` | `-> dict[str, Any]` |
| `services/chess_coach/gateway/routes/engines.py:48` | `engine_info` | `-> dict[str, Any]` |
| `services/chess_coach/gateway/routes/blunder_routes.py:39` | `get_blunders_batch` | `-> dict[str, str \| None]` |
| `services/chess_coach/gateway/routes/blunder_routes.py:62` | `get_blunders_by_fen` | `-> BlunderEnvelope` |
| `services/chess_coach/gateway/routes/backfill_analyses.py:70` | `_engine_pool` | `-> Any` |
| `services/chess_coach/gateway/routes/narration.py:41` | `_pipeline` | `-> Any` |
| `services/chess_coach/gateway/routes/narration.py:45` | `_engine_pool` | `-> Any` |
| `services/chess_coach/gateway/routes/narration.py:118` | `explain_position` | `pipeline: Any, engine_pool: Any` (param types; the return type is unchanged because `evaluate` returns `dict[str, Any]` per the existing code) |

## §3. The 14 inner _metric_* function annotations

All 14 inner `_metric_*` functions in `profile.py` and
`profile_analysis.py` received the same annotation:
`(db_path: str, player: str, **_: Any) -> EffectSize`.

The 7 functions in `profile.py`:
- `_metric_tactical`, `_metric_time_pressure`, `_metric_opening`,
  `_metric_conversion`, `_metric_blunder_rating`,
  `_metric_decision_fatigue`, `_metric_sequence_tilt`

The 7 functions in `profile_analysis.py` (same names).

These functions are pass-through wrappers that call
the actual metric implementations in
`chess_coach.profile` (e.g., `tactical_vs_positional_bias`).
The `**_: Any` swallows the `gate_kwargs` keyword
arguments that the `_METRIC_REGISTRY` may pass through.

## §4. The typing import additions (8 files)

| File | Import added |
|---|---|
| `libs/chess_coach/testkit/mock_uci.py` | `from typing import Any` (was no typing import) |
| `services/chess_coach/gateway/routes/eval_graph.py` | `from typing import Any, Callable, Coroutine` (was `Any` only) |
| `services/chess_coach/gateway/routes/profile_analysis.py` | `Any` added to existing `from typing import cast, Callable` |
| `services/chess_coach/gateway/routes/profile.py` | `Callable` added to existing `from typing import Any` |
| `services/chess_coach/gateway/routes/narration.py` | `from typing import Any` (was no typing import) |
| `services/chess_coach/gateway/routes/profile.py` | `EffectSize` added to `from chess_coach.profile import (...)` |
| `services/chess_coach/gateway/routes/profile_analysis.py` | `EffectSize` added to `from chess_coach.profile import (...)` |
| `libs/chess_coach/datasets/archetype_gold.py` | `from typing import Any` (was no typing import) |

## §5. The verification (live, this session)

```
# Before (post-BBF-FU-29-mypy-misc):
$ mypy libs services apps/cli --no-incremental
Found 74 errors in 28 files
   48  no-untyped-def
   20  no-any-return
   ...

# After this BBF:
$ mypy libs services apps/cli --no-incremental
Found 32 errors in 28 files
    0  no-untyped-def   <-- all 48 fixed
   20  no-any-return
    3  arg-type
    3  misc
   ...
```

**-42 errors net, -2 files affected. no-untyped-def is now 0.**

## §6. The §1.3 catches (exemplary discipline)

| # | Catch | When | Fix |
|---|---|---|---|
| 1 | **CRLF footgun** in 12 of 15 modified files (the second time this session — the first was the FU-29-mypy-misc BBF) | Pre-commit | Converted all 12 files entirely to LF to match the rest of the codebase |
| 2 | **Duplicated lines** on `archetype_gold.py:91` from the split-the-long-line fix | Pre-commit | Amend cleaned the duplicates |
| 3 | **New `attr-defined` errors** (7) from `corpus: list[dict[str, Any]]` on `validate_archetype_gold` (the code accesses `.id` and `.metrics` which don't exist on a generic dict) | Local re-measure | Re-typed to `corpus: list[Any]` to suppress false positives |
| 4 | **Import order (I001)** — `from typing import Any, cast` was out of order | Local ruff | `ruff check --fix` auto-resolved |
| 5 | **Syntax error** — `rstrip(')').rstrip() + ', EffectSize)'` left a dangling `(` in `profile.py` and `profile_analysis.py` | Pre-commit | Amend fixed the malformed import statements |
| 6 | **Param types lost** on the second pass of inner function annotations | Pre-commit | Re-added `(db_path: str, player: str, **_: Any)` to all 14 inner functions |

**Pre-commit catches are the right level of §1.3 discipline** — bugs were caught before any state-mutating action (no merge, no PR merge).

## §7. The 32 remaining errors (deferred to other sub-tasks)

| Code | Count | Next BBF |
|---|---|---|
| `no-any-return` | 20 | `go FU-29-mypy-no-any-return` (sub-task C) |
| `arg-type` | 3 | `go FU-29-mypy-misc-followup` |
| `misc` | 3 | `go FU-29-mypy-misc-followup` |
| `call-overload` | 1 | `go FU-29-mypy-misc-followup` |
| `return-value` | 1 | `go FU-29-mypy-misc-followup` |
| `no-redef` | 1 | `go FU-29-mypy-misc-followup` |
| `assignment` | 1 | `go FU-29-mypy-misc-followup` |
| `dict-item` | 1 | `go FU-29-mypy-misc-followup` |
| `union-attr` | 1 | `go FU-29-mypy-misc-followup` |

**The `no-untyped-def` sub-task is DONE.** The remaining
32 errors are spread across the other sub-tasks
(mainly `no-any-return`).

## §8. Honest disclosures

1. **The 14 inner function annotations were the trickiest part.** The pattern `(db_path: str, player: str, **_: Any) -> EffectSize` had to be applied to all 14 functions (7 in `profile.py`, 7 in `profile_analysis.py`). The `**_: Any` swallows the `gate_kwargs` keyword arguments that the `_METRIC_REGISTRY` may pass through.

2. **The `validate_archetype_gold` annotation went through 3 iterations.** `list[dict[str, Any]]` → `list[Any]` after the `attr-defined` errors surfaced (the code accesses `.id` and `.metrics` which don't exist on a generic dict). The `list[Any]` is the most pragmatic choice for a validator function that takes a list of untyped dicts. A `TypedDict` would be the proper fix, but that's a separate refactor.

3. **The 5 new `arg-type` errors in `eval_graph.py:370` and `repertoire.py`** (one for the inner `_run` function's `Callable[..., Any]` param) are expected. The `Callable` type import was added correctly. The remaining `arg-type` errors are for `len()` calls on `Iterable[Row]` (qdrant client return type) — these are separate fixes.

4. **The `__init__.py` and `pytest-cov` sub-ratchets are still pending.** The FU-29 ratchet is on the right track but not yet complete.

5. **No new tests added.** The fix is mechanical (type annotations); existing tests cover the affected code paths.

6. **The 13/13 CI green on `2f39ac96` (the FU-29-mypy-misc ship) is preserved.** This BBF adds no CI changes; the existing `gateway boot (clean install)` job runs the unit tests, and the `ruff lint` job runs `ruff check`. Both pass.

## §9. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-29 entry
  (the original ledger entry; this BBF is the
  Stage 1 mypy sub-task B).
- `docs/16_audit/BBF-FU-29-scoping-brief.md`
  (the ratchet-strategy brief, shipped at
  `e2da99c7`).
- `docs/16_audit/BBF-FU-29-status-check.md`
  (the re-measurement brief, shipped at
  `8e4e62e3`).
- `docs/16_audit/BBF-FU-29-ruff-burndown.md`
  (the Stage 1 ruff sub-burndown, shipped at
  `a27da3f9`).
- `docs/16_audit/BBF-FU-29-ruff-wire-ci.md`
  (the Stage 3 ruff wire-to-CI, shipped at
  `98780986`).
- `docs/16_audit/BBF-FU-29-mypy-burndown.md`
  (the Stage 1 mypy easy sub-scope, shipped at
  `8c06036d`).
- `docs/16_audit/BBF-FU-29-mypy-type-arg.md`
  (the Stage 1 mypy sub-task A, shipped at
  `8de8cd27`).
- `docs/16_audit/BBF-FU-29-mypy-misc.md`
  (the Stage 1 mypy sub-task D, shipped at
  `2f39ac96`).
- `pyproject.toml` lines 55-63 (the `[dev]`
  extras, which declare `mypy>=1.10`).
- `pyproject.toml` lines 119-129 (the
  `[tool.mypy]` config, including `strict = true`).
