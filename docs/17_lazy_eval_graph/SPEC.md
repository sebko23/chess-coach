# Lazy Eval-Graph — Strategic Spec

**Sprint**: BBF-22 onwards
**Trigger**: BBF-21 demonstrated that the 610-game full-corpus backfill is bounded by Stockfish throughput regardless of gather orchestration. At 6000 games this becomes a 33+ hour wall-clock that no user will wait through. Pre-computing analyses for every ply of every imported game is the wrong architecture for a corpus larger than ~200 games.
**Goal**: make PGN import a **seconds-scale** operation regardless of corpus size, and make eval-graph rendering fast for the user's actual viewing pattern, by switching from eager pre-compute to lazy on-demand analysis with cache.
**Status**: spec, awaiting user approval.

---

## The problem in numbers

| Corpus size | Eager pre-compute at depth 6, MAX_WORKERS=4 |
|---|---|
| 200 games × 50 plies | ~17 min |
| 610 games × 78 plies (current) | ~3.4 h |
| 1,000 games × 78 plies | ~5.5 h |
| 6,000 games × 78 plies | **33 h** |
| 60,000 games × 78 plies | 14 d |

The current `/v1/import/pgn` route pre-computes analyses inline. Importing 6000 games would either (a) block the import HTTP request for 33 hours — a request timeout is typically 30-300 s, so the request would die — or (b) require an out-of-band job queue that the user has to poll. Both are bad UX. The backfill route has the same problem.

**Pre-computing analyses at all is wrong for a corpus this size.** Most users only ever view a tiny fraction of positions. Pre-computing everything is wasted work.

## The new architecture: lazy with cache

Three principles:

1. **PGN import does NO analysis.** It parses the PGN, walks the mainline, INSERTs the `games` and `positions` rows, and returns. The `analyses` table is empty for the new game. Import time: **seconds** regardless of corpus size.
2. **Eval-graph is computed on first request and cached.** When the user opens a game's eval-graph, the route computes the missing analyses, INSERTs them, and returns. Subsequent requests hit the cache.
3. **Cache scope: per-(game, ply, depth).** Cache key is the analyses.id (`f"{game_id}:{ply}:stockfish:{depth}"`). Re-importing a game is idempotent because `INSERT OR IGNORE` is used.

This matches the actual user viewing pattern: import many games, view a few. The 6000-game import is now **seconds**. The first time a user opens a game's eval-graph, they wait ~1-2 s for the analyses to compute. After that it's instant.

## What changes

### Backend

- **`/v1/import/pgn`**: drop the per-game analyses gather. After inserting `positions`, return immediately. Response shape keeps `analyzed_count` and `analysis_failed_count` for back-compat, but they always return `0` and the import is successful.
- **`/v1/import/backfill-analyses`**: keep as-is. It's the explicit "pre-compute everything" path for users who want a full corpus (e.g. for ML training, or for offline use). Add a deprecation note in the docstring that lazy is now the default.
- **`/v1/games/{game_id}/eval-graph`**: the existing route. It already does `LEFT JOIN analyses`. With lazy: when the join returns no row for a ply, the route computes the analysis for that ply, INSERTs it, and returns the score. Compute is bounded by `positions_count` (max 200 plies per game; the gather fits in memory).
- **New route `POST /v1/games/{game_id}/eval` (optional, future)**: bulk-precompute a game on first view. The eval-graph route can call this internally on cache miss, or the GUI can call it directly to warm the cache for a game the user clicks into.

### Frontend

- **No changes to the GUI eval-graph renderer**. It already calls `GET /v1/games/{id}/eval-graph?depth=6`. The new lazy behavior is transparent.
- **`/v1/import/pgn` no longer shows `Backfill: N games, M plies analyzed`**. The success banner just says `Imported N games`. Users who want full-corpus pre-compute click the existing Backfill button.
- **Optional: add a "Compute full analysis" button on the game detail view**, for users who want to pre-compute a single game's analyses. Calls `POST /v1/games/{id}/eval`. This is a 2-3 line addition.

### Database

- **No schema changes.** The `analyses` table is the cache. Empty analyses rows for a game simply mean "not yet computed". The eval-graph LEFT JOIN already handles this.
- **No migration of the existing 610 games.** They keep their pre-computed analyses. New games are lazy.

### Caching semantics

- **Cache key**: `(game_id, ply, engine_id, depth)`. Encoded as `analyses.id = f"{game_id}:{ply}:{engine_id}:{depth}"`.
- **Cache invalidation**: none for now. If a user wants to re-analyze at a new depth, they pass `?depth=N` in the URL, which produces a different cache key. The old `analyses` rows at the old depth stay in the table (harmless; they don't get read again unless the same depth is requested).
- **Cache eviction**: not implemented. With 6000 games × 200 plies × 1 depth = 1.2M rows max, the table stays small (~100 MB). For deeper plies, future eviction is a separate concern.

## The four sprints to land this

### BBF-22: backend lazy eval-graph (the load-bearing piece)
- Modify `pgn_import.py`: drop the per-game analyses gather. Keep all other behavior (positions INSERT, PGN parsing, response shape).
- Modify `eval_graph.py`: on cache miss (no analysis row for a position), compute the analysis inline, INSERT it, return. Add a per-request in-memory dedup so the same `(game_id, ply, depth)` doesn't get analyzed twice if it's requested concurrently.
- Verify: import a 50-ply PGN → returns in <1s with `analyzed_count=0`. GET eval-graph → computes 51 analyses on first call, instant on second call. Both `score_cp` values match the pre-BBF-22 baseline within ±2 cp (Stockfish is deterministic at the same depth and seed).

### BBF-23: GUI integration
- Update the import success banner: drop the analysis-count text. Keep the `Imported N games` part.
- Verify: TS clean, no behavior regression on the import path.

### BBF-24: optional "Compute full analysis" button on game detail
- Add a button to the game detail view that calls `POST /v1/games/{id}/eval` and shows a progress banner.
- The button is for users who want eager pre-compute on a specific game they're about to study deeply.
- Skip this sprint if scope is tight. The lazy default is enough for the 6000-game scaling problem.

### BBF-25: stress test with 6000-game synthetic PGN
- Generate a 6000-game PGN file (1 PGN with 6000 games concatenated).
- Time the import. Expected: < 60 s wall-clock (was: 33+ h).
- Time the eval-graph for 10 random games. Expected: 10-20 s for first call (lazy compute), < 100 ms for subsequent calls.
- Document the new perf curve in the perf-debug skill.

## What this does NOT solve

- **Phase 6 (PDF/Vision)**: separate content-ingest project. Out of scope.
- **Multi-gateway load balancing**: still useful for a corpus where many users view different games concurrently. A future sprint.
- **Maia (neural net) engine**: out of scope. Maia would need its own `analyses.engine_id` cache entries; the cache key already supports it.
- **Narration pipeline on demand**: the LLM narration is a separate pipeline that runs on top of analyses. Lazy analyses means lazy narration too, which is fine — narrations aren't pre-computed today.

## What this DOES solve

- **6000-game imports become seconds-scale.** The hard scaling problem goes away.
- **No more hours-long Backfill button.** The button still exists for full-corpus pre-compute, but the default flow doesn't use it.
- **Eval-graph is fast for the actual viewing pattern.** Users see a 1-2 s delay on first game open, instant thereafter.
- **Code path is simpler.** The pgn_import route no longer needs the semaphore, gather, or per-game error handling. The backfill route becomes the explicit "pre-compute everything" path with a clear contract.
- **The DB write bottleneck (BBF-19's 1.3× ceiling) goes away for the import path.** Analyses writes are now driven by user viewing, which is naturally rate-limited.

## Open questions for the user

1. **Cache eviction policy.** For a corpus that grows large (10k+ games), should there be a TTL or an LRU eviction? **Default recommendation: no eviction** for v1. Re-evaluate when the table exceeds 10 GB.
2. **Per-request in-memory dedup window in eval-graph.** If two users open the same game at the same time, do we want to dedup in-memory (one analyze call, two responses) or let both go (two analyze calls, one wins on `INSERT OR IGNORE`)? **Default recommendation: in-memory dedup** via a short-lived (5-60 s) `dict[cache_key, asyncio.Future]` to avoid wasted Stockfish work.
3. **Max ply depth for lazy eval-graph.** Should we cap it at the import-time `max_plies` (default 200), or let the user request deeper? **Default recommendation: cap at the `max_plies` of the most recent import for that game.** For a PGN imported with `max_plies=50`, only plies 0-50 are in the `positions` table; deeper plies don't exist.
4. **The `Backfill analyses` button.** Keep it for explicit "compute everything" workflows, or remove it? **Default recommendation: keep it** but reword the tooltip to "Pre-compute analyses for all games. Slower than lazy; only needed for offline use or training data."

## What BBF-21 (just-shipped refactor) does in this new world

- BBF-21's three-phase pipeline is **the right shape for the explicit pre-compute path** (backfill route). It does NOT get removed — it just becomes the implementation of a less-frequently-used endpoint.
- The `pgn_import.py` route, which BBF-21 does NOT touch, is what BBF-22 simplifies. The async gather + semaphore in `pgn_import.py` go away; the route becomes synchronous PGN parsing + bulk INSERT.

## Acceptance criteria for the whole pivot

1. **6000-game PGN import < 60 s wall-clock.** Verified in BBF-25.
2. **First eval-graph call for a new game < 2 s for a 50-ply game, depth 6.** Verified in BBF-22.
3. **Second eval-graph call for the same game < 100 ms.** Cache hit. Verified in BBF-22.
4. **No deadlocks, no FK violations, no orphan analyses.** Verified per-sprint.
5. **All four previous BBF tests still pass** (1-ply, 9-ply, 18-ply import + backfill). No regression.
6. **`analyzed_count` always returns 0 on import.** Documented in the route's response shape.

## Effort estimate

- BBF-22: 4-6 hours. The hard part is the lazy eval-graph; the import simplification is trivial.
- BBF-23: 30 min. Just text changes.
- BBF-24 (optional): 1-2 hours.
- BBF-25: 2-3 hours. Synthetic PGN generation, perf measurement, skill update.

Total: **~1 working day** for the full pivot, or **~5 hours** if we skip BBF-24.

## Why this is the right strategic pivot

The handoff listed "L-2-real (50+ page gold set) or Phase 6 (PDF/Vision via Architecture E)" as the strategic options. After reading the docs, both of those are content-ingest projects (PDFs → FENs) — different problem from scaling engine analysis to 6000 games. The right strategic pivot for the **scaling problem you raised** is the lazy-eval-graph architecture described above. It's:

- **The minimum architectural change** that solves the problem.
- **Backwards compatible** with the existing 610 games (no migration).
- **Optional per-game eager pre-compute** preserved (Backfill button).
- **Coach-aligned**: "look at your game" is a single click, "compute everything" is explicit.

If you also want to do Phase 6 (PDF/Vision), that's a separate, larger sprint. The lazy-eval-graph architecture makes Phase 6's compute footprint smaller (PDFs add games, not analyses), so doing lazy first is the right ordering.

---

**Next action**: get your approval to start BBF-22.
