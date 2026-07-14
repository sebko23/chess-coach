"""Routes for per-game evaluation graphs.

BBF-22: lazy eval-graph. On cache miss (no analysis row for a position),
the route computes the analysis inline via the engine pool, INSERTs it,
and returns. Cache key is analyses.id (f\"{game_id}:{ply}:{engine_id}:{depth}\").
INSERT OR IGNORE makes concurrent first-views safe: only one analysis runs
per cache key.

A short-lived in-memory dedup avoids redundant Stockfish work when two
concurrent requests ask for the same missing position. The dedup window
is 60s; after that, if a second request arrives, it will re-analyze.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from chess_coach.errors.codes import ErrorCode
from chess_coach.gateway.auth import require_bearer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["games"], dependencies=[Depends(require_bearer)])


class EvalPoint(BaseModel):
    ply: int
    score_cp: int | None = None
    score_mate: int | None = None
    move_san: str | None = None
    classification: str | None = None


# In-memory dedup for in-flight analyses. Key: (game_id, ply, engine_id, depth).
# Value: (future, expiry_monotonic). When expiry is past, the entry is stale
# and the next caller will start a fresh analysis. asyncio.Future is used so
# concurrent callers await the same Stockfish result instead of duplicating.
_inflight: dict[tuple[str, int, str, int], tuple[asyncio.Future, float]] = {}
_DEDUP_TTL_S = 60.0

# Async lock to make the get-then-put sequence in _coalesce_analyze atomic.
# Without this, two concurrent first-views on the same key could both pass
# the "_dedup_get returned None" check and both register as the leader,
# which would defeat the entire purpose of the dedup. The lock holds for
# only the few microseconds of the dict round-trip; the Stockfish analysis
# itself runs OUTSIDE the lock, so this is not a bottleneck on the hot path.
_dedup_lock: asyncio.Lock | None = None


def _get_dedup_lock() -> asyncio.Lock:
    """Lazily construct the dedup lock.

    asyncio.Lock must be created inside a running event loop; doing so
    at module import would fail under pytest-asyncio's function-scoped
    loops. We lazily bind on first use.
    """
    global _dedup_lock
    if _dedup_lock is None:
        _dedup_lock = asyncio.Lock()
    return _dedup_lock


def _dedup_get(key: tuple[str, int, str, int]) -> asyncio.Future | None:
    """Return the in-flight future for this cache key, or None if none."""
    entry = _inflight.get(key)
    if entry is None:
        return None
    future, expiry = entry
    if time.monotonic() > expiry:
        # Stale entry. Drop it.
        _inflight.pop(key, None)
        return None
    if future.done():
        # Completed future lingering in the dict. Drop it.
        _inflight.pop(key, None)
        return None
    return future


def _dedup_put(key: tuple[str, int, str, int], future: asyncio.Future) -> None:
    _inflight[key] = (future, time.monotonic() + _DEDUP_TTL_S)


async def _coalesce_analyze(
    key: tuple[str, int, str, int],
    coro_factory,
) -> Any:
    """Either await an in-flight analysis for ``key`` or run a fresh one.

    Race-safe: a single asyncio.Lock (``_get_dedup_lock()``) guards the
    check-then-register sequence so two concurrent first-views on the
    same key cannot both become the leader.

    The leader creates an asyncio.Future, registers it, and runs
    ``coro_factory()`` outside the lock; followers await the same future.
    Whichever follower count arrives, exactly one Stockfish call runs.

    Cleanup: the leader's ``finally`` removes the dict entry regardless
    of outcome (success, exception, cancellation) so the next caller
    after this analysis finishes gets a fresh start. The TTL is just a
    safety valve for the rare case where the leader crashed hard enough
    to skip the finally (which should not happen in CPython but is cheap
    insurance).
    """
    lock = _get_dedup_lock()
    async with lock:
        existing = _dedup_get(key)
        if existing is not None:
            fut = existing
            is_leader = False
        else:
            loop = asyncio.get_event_loop()
            fut = loop.create_future()
            _dedup_put(key, fut)
            is_leader = True

    if is_leader:
        try:
            result = await coro_factory()
            if not fut.done():
                fut.set_result(result)
            return result
        except BaseException as exc:  # noqa: BLE001 - propagate to all waiters
            if not fut.done():
                fut.set_exception(exc)
            raise
        finally:
            # Drop the entry so the next caller gets a fresh analysis.
            # Use pop-with-default to avoid races with another coroutine
            # that already replaced our entry (which can happen if the
            # leader crashed and a follower somehow slipped in -- but
            # the lock above prevents that, so this is just hygiene).
            _inflight.pop(key, None)
    else:
        # Follower: await the leader's future. If the leader raises or
        # is cancelled, we receive the same exception.
        return await fut


# Module-level cache for the analyses schema. Set on first call; never
# invalidated because the schema is fixed for the gateway lifetime (new
# columns only arrive via migrations, which require a restart).
_analyses_cols_cache: list[tuple] | None = None


async def _analyses_table_columns(db_path: str) -> list[tuple]:
    """PRAGMA table_info(analyses): (cid, name, type, notnull, dflt_value, pk).

    Memoized at module level. Safe because the analyses schema is fixed
    for the lifetime of the gateway process.
    """
    global _analyses_cols_cache
    if _analyses_cols_cache is not None:
        return _analyses_cols_cache
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("PRAGMA table_info(analyses)")
        _analyses_cols_cache = list(await cur.fetchall())
    return _analyses_cols_cache


def _build_analyses_row(
    position_id: str, depth: int, result: Any, analyses_cols: list[tuple] | None = None
) -> dict[str, object]:
    """Build the analyses row dict from an AnalysisResult. Pure function.

    If analyses_cols is provided, backfill any NOT NULL column that is
    missing from the row (a future migration might add a column we don't
    know about). The hard-coded row is the BBF-22 baseline; the backfill
    is the BBF-8 safety net.
    """
    score_cp = None
    score_mate = None
    if result.pvs and result.pvs[0].score:
        sc = result.pvs[0].score
        if sc.kind == "cp":
            score_cp = sc.value
        elif sc.kind == "mate":
            score_mate = sc.value
    best_move = (
        result.pvs[0].moves[0]
        if result.pvs and result.pvs[0].moves
        else None
    )
    pv_moves = (
        ",".join(result.pvs[0].moves)
        if result.pvs and result.pvs[0].moves
        else None
    )
    row: dict[str, object] = {
        "id": f"{position_id}:stockfish:{depth}",
        "position_id": position_id,
        "engine_id": "stockfish",
        "depth": depth,
        "score_cp": score_cp,
        "score_mate": score_mate,
        "best_move": best_move,
        "pv_moves": pv_moves,
        "result_json": result.model_dump_json(),
        "classification": "book",
        "cp_delta": 0,
    }
    if analyses_cols is not None:
        notnull = {c[1] for c in analyses_cols if c[3] == 1}
        for col in notnull:
            if col in row:
                continue
            default = next((c[4] for c in analyses_cols if c[1] == col), None)
            if default is not None and default != "":
                continue
            row[col] = ""
    return row


async def _analyze_one_position(
    db: aiosqlite.Connection,
    pool: Any,
    AnalysisRequest: Any,
    analyses_cols: list[tuple],
    position_id: str,
    fen: str,
    depth: int,
) -> bool:
    """Run Stockfish on one position and INSERT the result using a shared
    aiosqlite connection. Caller is responsible for commit/rollback.

    This is the BBF-22 fix for the "can't start new thread" failure: the
    original design opened a new aiosqlite connection per analysis, each
    of which spawns a background thread to bridge sqlite3's sync API to
    asyncio. With 19 concurrent analyses (a 19-ply PGN), the per-process
    thread limit was hit. Sharing one connection across the whole gather
    avoids this and is what the original pgn_import.py did.
    """
    try:
        req = AnalysisRequest(fen=fen, depth=depth, engine_id="stockfish")
        result = await pool.analyze(req, "stockfish")
    except Exception as exc:
        logger.warning(
            "eval-graph %s: analyze failed: %s", position_id, exc,
        )
        return False
    if not result.pvs:
        logger.warning(
            "eval-graph %s: stockfish returned no PVs", position_id,
        )
        return False
    row = _build_analyses_row(position_id, depth, result, analyses_cols)
    cols_csv = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    sql = f"INSERT OR IGNORE INTO analyses ({cols_csv}) VALUES ({placeholders})"
    try:
        await db.execute(sql, list(row.values()))
        return True
    except Exception as exc:
        logger.warning(
            "eval-graph %s: analyses insert failed: %s", position_id, exc,
        )
        return False


@router.get("/v1/games/{game_id}/eval-graph", response_model=list[EvalPoint])
async def get_eval_graph(
    game_id: str,
    request: Request,
    depth: int = 6,
) -> list[EvalPoint]:
    """Return per-position evaluation scores for a game, ordered by ply.

    BBF-22: lazy mode. For each position in the game:
      - if an analyses row already exists at the requested depth, return it.
      - otherwise, run Stockfish inline, INSERT the result, and return it.

    The first call for a new game runs N Stockfish analyses (one per ply).
    Subsequent calls are cache hits. With CHESS_COACH_MAX_WORKERS=4 the
    first call for a 50-ply game takes ~5s; subsequent calls < 100ms.
    """
    settings = request.app.state.gateway.settings
    db_path = str(settings.sqlite_path)

    pool = getattr(request.app.state, "engine_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": ErrorCode.SERVICE_UNAVAILABLE.value,
                "message": "engine pool not initialized; cannot compute lazy analyses",
            },
        )

    from chess_coach.protocol_types.analysis import AnalysisRequest
    analyses_cols = await _analyses_table_columns(db_path)

    # Phase 1: read positions LEFT JOIN analyses. Identify the cache misses.
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT p.ply, p.fen, p.id AS position_id, a.score_cp, a.score_mate, "
            "p.move_san, a.classification "
            "FROM positions p "
            "LEFT JOIN analyses a ON a.position_id = p.id "
            "  AND a.engine_id = 'stockfish' AND a.depth = ? "
            "WHERE p.game_id = ? ORDER BY p.ply ASC",
            (depth, game_id),
        )
        rows = list(await cur.fetchall())

    if not rows:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.NOT_FOUND.value,
                "message": f"No positions found for game {game_id}",
            },
        )

    # Phase 2: gather all missing analyses. ONE shared aiosqlite connection
    # is used for the INSERTs (avoids the per-connection background-thread
    # explosion that hit the per-process thread limit on a 19-ply PGN).
    # The Stockfish calls themselves are serialized by the pool's semaphore.
    missing: list[tuple[str, int, str]] = []
    out_by_ply: dict[int, dict] = {}
    for r in rows:
        ply = r["ply"]
        if r["score_cp"] is None and r["score_mate"] is None:
            missing.append((r["position_id"], ply, r["fen"]))
            out_by_ply[ply] = {
                "ply": ply,
                "score_cp": None,
                "score_mate": None,
                "move_san": r["move_san"],
                "classification": None,
            }
        else:
            out_by_ply[ply] = {
                "ply": ply,
                "score_cp": r["score_cp"],
                "score_mate": r["score_mate"],
                "move_san": r["move_san"],
                "classification": r["classification"],
            }

    if missing:
        async with aiosqlite.connect(db_path) as db:
            # BBF-36: dedup concurrent first-views on the same
            # (game_id, ply, engine_id, depth) into one Stockfish call.
            # The gather still launches N tasks (one per missing
            # position, plus duplicate-key duplicates), but every task
            # for the same key awaits the same asyncio.Future created
            # by the leader. The pool's semaphore bounds the unique
            # analyses, not the awaiters.
            tasks = []
            for position_id, ply, fen in missing:
                key = (game_id, ply, "stockfish", depth)

                async def _run(
                    pid=position_id, f=fen, p=ply, k=key,
                ):
                    # Each task binds its own copy of pid/f/p/k via
                    # default-arg closure so the gather's shared
                    # ``for`` loop variable doesn't trip the late-bind
                    # bug.
                    return await _coalesce_analyze(
                        k,
                        lambda: _analyze_one_position(
                            db,
                            pool,
                            AnalysisRequest,
                            analyses_cols,
                            pid,
                            f,
                            depth,
                        ),
                    )

                tasks.append(_run())

            await asyncio.gather(*tasks, return_exceptions=True)
            await db.commit()

        # Phase 3: re-read the cache to pick up the freshly-inserted rows.
        # One query for all the missing position_ids.
        position_ids = [pid for pid, _ply, _fen in missing]
        placeholders = ",".join("?" for _ in position_ids)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"SELECT position_id, score_cp, score_mate, classification "
                f"FROM analyses WHERE position_id IN ({placeholders}) "
                f"AND engine_id = 'stockfish' AND depth = ?",
                (*position_ids, depth),
            )
            for r in await cur.fetchall():
                # The position_id is "{game_id}:{ply}"; extract ply.
                last_colon = r["position_id"].rfind(":")
                try:
                    ply = int(r["position_id"][last_colon + 1:])
                except (ValueError, IndexError):
                    continue
                if ply in out_by_ply:
                    out_by_ply[ply] = {
                        "ply": ply,
                        "score_cp": r["score_cp"],
                        "score_mate": r["score_mate"],
                        "move_san": out_by_ply[ply]["move_san"],
                        "classification": r["classification"],
                    }

    return [out_by_ply[r["ply"]] for r in rows]
