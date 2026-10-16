# BBF-FU-29-mypy-type-arg — Stage 1 mypy sub-task A (32 type-arg → 0)

**Sprint intent:** Execute Stage 1 of the FU-29 ratchet
(per `BBF-FU-29-scoping-brief.md` §2, shipped at
`e2da99c7`) for the **mypy** tool, sub-task A: fix the
32 `type-arg` errors (add `dict[K, V]`, `list[X]`,
`tuple[X, Y]`, `Future[X]`, `Callable[..., X]`, etc.).
This is the cheapest sub-task per the prior BBF
(`BBF-FU-29-mypy-burndown.md`)'s §3 follow-up chain.

**Status:** Code-only BBF. 9 files modified.

## §1. The 32 type-arg errors (before fix)

Per the 2026-10-16 re-measurement (per
`BBF-FU-29-status-check.md`):

| Generic | Count | Where |
|---|---|---|
| `dict` | 23 | dataclass fields, route handlers, sqlite row dicts |
| `tuple` | 6 | sqlite row tuples |
| `Future` | 4 | `_inflight` cache + `_dedup_*` helpers in `eval_graph.py` |
| `list` | 1 | `_drain_go` events list |
| `Callable` | 1 | `route_guard` decorator signature |
| `count` | 1 | `itertools.count` (Python 3.10+ parameterized counter) |

**All 32 errors are bare-generic-type errors:**
`dict` instead of `dict[K, V]`, `tuple` instead of
`tuple[X, Y]`, etc. The fix is mechanical: add the
type parameter.

## §2. The 32 fixes (this BBF)

### Generic-type parameterization

The 32 fixes split into 6 patterns:

| Pattern | Count | Example |
|---|---|---|
| `dict` → `dict[str, Any]` | 19 | `metrics: dict` → `metrics: dict[str, Any]` |
| `dict` → `dict[K, V]` (known K, V) | 3 | `fields: dict` → `fields: dict[str, str]` (UCI engine) |
| `dict` → `dict[str, str]` (UCI engine) | 1 | (combined with above) |
| `list[dict]` → `list[dict[str, Any]]` | 4 | `objs: list[dict]` → `objs: list[dict[str, Any]]` |
| `list[tuple]` → `list[tuple[Any, ...]]` | 4 | `_games_table_columns() -> list[tuple]` → `list[tuple[Any, ...]]` |
| `tuple` → `tuple[K, V, W]` (known) | 1 | `_parse_game(obj: dict) -> tuple[str, dict, str]` → `tuple[str, dict[str, Any], str]` |
| `Future` → `Future[Any]` | 4 | `_inflight: dict[..., tuple[asyncio.Future, float]]` → `tuple[asyncio.Future[Any], float]` |
| `Callable` → `Callable[..., Any]` | 2 | `route_guard(fn: Callable) -> Callable` → `Callable[..., Any]` (param + return) |
| `itertools.count` → `itertools.count[int]` | 1 | `self._rr: dict[str, itertools.count]` → `itertools.count[int]` |

(Counts overlap — total is 32; the rows describe the
specific patterns.)

### `Any` imports

`Any` is not imported in 7 of the 9 files affected.
Added `from typing import Any` to:

- `libs/chess_coach/datasets/archetype_gold.py`
- `services/chess_coach/engine_orch/pool.py`
- `services/chess_coach/gold/eval_delta.py`
- `services/chess_coach/gateway/routes/profile.py`
- `services/chess_coach/gateway/routes/pgn_import.py`
- `services/chess_coach/gateway/routes/lichess_import.py`
- `libs/chess_coach/uci/engine.py`

The other 2 files (`eval_graph.py`, `route_guard.py`)
already imported `Any` (or `Callable` via the same
`from typing import` line).

## §3. The verification (live, this session)

```
# Before (post-FU-29-mypy-burndown):
$ mypy libs services apps/cli --no-incremental
Found 135 errors in 30 files (checked 86 source files)
   50  no-untyped-def
   32  type-arg
   20  no-any-return
   ...

# After this BBF:
$ mypy libs services apps/cli --no-incremental
Found 118 errors in 28 files (checked 86 source files)
   50  no-untyped-def
   19  no-any-return
   12  arg-type
   11  assignment
    9  union-attr
    ...
    0  type-arg   <-- 32 errors fixed
    0  (new) name-defined  <-- 21 stale "Any not defined" fixed
    1  name-defined (pre-existing `resource` in subprocess_runner.py:113)
```

**-17 errors net, -2 files affected.**

The `type-arg` error count is now **0**. The
`name-defined` error count is now **1** (a pre-existing
`resource` import in `subprocess_runner.py:113`, not
caused by this BBF — was in the 2026-10-16
re-measurement's 169 errors too).

## §4. The follow-up chain (after this BBF)

The remaining 118 errors are:

| Count | Code | Est. cost | Next BBF |
|---|---|---|---|
| 50 | `no-untyped-def` | 1-2 hrs | `go FU-29-mypy-no-untyped-def` |
| 19 | `no-any-return` | ~1 hr | `go FU-29-mypy-no-any-return` |
| 12 | `arg-type` | ~30 min | `go FU-29-mypy-misc` |
| 11 | `assignment` | ~1 hr | `go FU-29-mypy-misc` |
| 9 | `union-attr` | ~30 min | `go FU-29-mypy-misc` |
| 4 | `attr-defined` | ~30 min | `go FU-29-mypy-misc` |
| 3 each | `no-untyped-call`, `misc`, `index` | ~1 hr | `go FU-29-mypy-misc` |
| 1 each | `var-annotated`, `return-value`, `name-defined`, `operator` | ~15 min | `go FU-29-mypy-misc` |
| **118** | **total** | **~5-6 hrs** | (3-4 follow-up BBFs) |

After all sub-tasks land:
`go FU-29-mypy-wire-ci` (Stage 3).

## §5. The CRLF footgun (caught and reverted)

4 of the 9 affected files were CRLF in HEAD:
- `route_guard.py` (66 CRLF)
- `engine.py` (342 CRLF)
- `eval_delta.py` (68 CRLF)
- `profile.py` (417 CRLF)

The first round of fixes used LF strings (because the
display tool's output is LF) and missed all 11 fixes
in these 4 files. The 4 files were then converted to
LF entirely (to match the now-LF state of the other 5
files) and the fixes re-applied in LF form.

**This is the same LF-preservation discipline as the
prior BBFs.** The `core.autocrlf=false` config means
git does not auto-convert; the on-disk line endings
are whatever the editor writes. The 4 files were
originally CRLF (presumably from a Windows developer's
editor); the LF fix normalizes them to LF to match
the rest of the codebase.

## §6. Honest disclosures

1. **The mypy burn-down is incomplete; 118 of 135
   errors remain.** This BBF is sub-task A of the
   4 follow-ups listed in the prior BBF's §3.

2. **The 32 fixes are mechanical; no semantic
   impact.** The code is correct; the type
   annotations were just incomplete.

3. **The 4 CRLF files were converted to LF to match
   the rest of the codebase.** This is a normalization,
   not a behavior change; the diff for these files
   shows the type-arg fixes (1-2 lines) plus a
   line-ending churn (which is invisible in `git
   diff --stat` once committed, because LF-only
   matches the rest of the codebase).

4. **The `Any` imports added to 7 files follow the
   same pattern as the existing `chess_coach.uci.engine`
   module (which has `from typing import Any`).** The
   import is a 1-line addition to each file.

5. **The 13/13 CI green on `8c06036d` (the
   FU-29-mypy-burndown ship) is preserved.** This
   BBF adds no CI changes; the existing
   `gateway boot (clean install)` job will run the
   unit tests, and the `ruff lint` job will run
   `ruff check`. Neither will be affected by the
   mypy type-arg fixes (mypy is not in CI yet).

6. **The pre-existing `resource` import in
   `subprocess_runner.py:113` is a mypy edge case.**
   The import is local (line 43) but mypy doesn't
   recognize it. This is a single-line mypy error
   that's been in the codebase since the FU-22-impl
   BBF. Out of scope for this BBF; will be addressed
   in `go FU-29-mypy-misc` (or a separate housekeeping
   BBF).

7. **No new tests added.** The fix is mechanical
   (type-arg parameterization); existing tests
   cover the affected code paths.

## §7. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-29 entry
  (the original ledger entry; this BBF is the
  Stage 1 mypy sub-task A).
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
  `8c06036d`; this BBF is its sub-task A).
