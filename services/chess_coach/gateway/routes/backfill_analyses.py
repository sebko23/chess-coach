"""Back-fill engine analyses for existing imported games.

POST /v1/import/backfill-analyses
Body: { game_ids?: list[str], depth: int = 8, max_plies: int = 200 }
Returns: { games_processed, games_skipped_no_pgn, plies_analyzed,
           plies_skipped_existing, positions_inserted, failures }

Idempotent: re-running the same request inserts only the missing positions
and analyses rows. Safe to call on a fully-imported corpus; cost is bounded by
`len(game_ids) * max_plies * stockfish_time_per_ply`.

BBF-21: previously this route processed games one at a time within a
single request, parallelizing only the per-ply analyses within ONE
game's gather(). For a 610-game corpus that meant ~610 sequential
gather() calls — each one tiny (50-200 plies), each one bounded by
the slowest single-ply analysis. The whole route took hours.

Now: walk all games' PGNs first (CPU-bound, fast), build one big
gather of stockfish analyses across ALL games, then per-game INSERT
the results in small transactions. Stockfish — the actual bottleneck
— runs truly in parallel across the pool's N slots (BBF-19). The
per-game commit pattern keeps each transaction small, avoiding the
long-transaction lock storms that pure gather() of analyses_rows
would cause.
"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

import chess
import chess.pgn
import aiosqlite
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..auth import require_bearer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/import", tags=["import"])


class BackfillRequest(BaseModel):
    game_ids: list[str] = Field(default_factory=list, description="If empty, back-fill all games with pgn_raw populated")
    depth: int = Field(8, ge=1, le=30)
    max_plies: int = Field(200, ge=1, le=1000)


class BackfillResponse(BaseModel):
    games_processed: int
    games_skipped_no_pgn: int
    plies_analyzed: int
    plies_skipped_existing: int
    positions_inserted: int
    failures: int


def _db_path(request: Request) -> str:
    return str(request.app.state.gateway.settings.sqlite_path)


def _engine_pool(request: Request):
    return request.app.state.engine_pool


def _walk_game_mainline(
    pgn_raw: str, max_plies: int
) -> list[tuple[int, str, str | None, str | None]] | None:
    """Return [(ply, fen, move_uci, move_san), ...] for the game's mainline.

    Returns None on parse failure. Pure function — no DB, no pool.
    BBF-21: this is called in Phase 0 for every game, so it must be
    fast and side-effect free. PGN parsing is CPU-bound, < 1ms per game.
    """
    try:
        pgn_io = io.StringIO(pgn_raw)
        game = chess.pgn.read_game(pgn_io)
    except Exception as exc:
        logger.warning("backfill: failed to parse PGN: %s", exc)
        return None
    if game is None:
        return None

    board = game.board()
    positions: list[tuple[int, str, str | None, str | None]] = [
        (0, board.fen(), None, None)
    ]
    ply = 1
    for move in game.mainline_moves():
        if ply > max_plies:
            break
        move_uci = move.uci()
        move_san = board.san(move)
        board.push(move)
        positions.append((ply, board.fen(), move_uci, move_san))
        ply += 1
    return positions


async def _analyze_one(
    pool: Any,
    AnalysisRequest: Any,
    fen: str,
    depth: int,
) -> Any:
    """Run stockfish on one FEN, return AnalysisResult or raise.

    Pure analyze — no DB writes. The pool.analyze() call is the slow
    part; it dispatches to one of N slots (BBF-19) and is bounded by
    the pool's semaphore.
    """
    req = AnalysisRequest(fen=fen, depth=depth, engine_id="stockfish")
    return await pool.analyze(req, "stockfish")


def _build_analyses_row(
    position_id: str, depth: int, result: Any
) -> dict[str, object]:
    """Build the analyses row dict from an AnalysisResult.

    Pure function. Schema columns are stable; if a future migration
    adds a column, introspect via PRAGMA like pgn_import.py does.
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
    return {
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


async def _insert_position(
    db: aiosqlite.Connection,
    position_id: str,
    game_id: str,
    prev_id: str | None,
    ply_idx: int,
    fen: str,
    move_uci: str | None,
    move_san: str | None,
) -> bool:
    try:
        cur = await db.execute(
            "INSERT OR IGNORE INTO positions "
            "(id, game_id, parent_id, fen, move_uci, move_san, ply, is_mainline) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (position_id, game_id, prev_id, fen, move_uci, move_san, ply_idx, 1),
        )
        return cur.rowcount == 1
    except Exception as exc:
        logger.warning(
            "backfill %s: positions insert failed for %s: %s",
            game_id, position_id, exc,
        )
        return False


async def _insert_analysis(
    db: aiosqlite.Connection,
    position_id: str,
    depth: int,
    result: Any,
) -> bool:
    row = _build_analyses_row(position_id, depth, result)
    cols_csv = ", ".join(row.keys())
    placeholders_sql = ", ".join("?" for _ in row)
    sql = f"INSERT OR IGNORE INTO analyses ({cols_csv}) VALUES ({placeholders_sql})"
    try:
        cur = await db.execute(sql, list(row.values()))
        return cur.rowcount == 1
    except Exception as exc:
        logger.warning(
            "backfill: analyses insert failed for %s: %s", position_id, exc,
        )
        return False


async def _existing_analysis_ids(
    db: aiosqlite.Connection, game_id: str
) -> set[str]:
    """Return the set of analyses.id for this game (joined via positions)."""
    cur = await db.execute(
        "SELECT a.id FROM analyses a JOIN positions p ON a.position_id = p.id "
        "WHERE p.game_id = ?",
        (game_id,),
    )
    return {row[0] for row in await cur.fetchall()}


@router.post(
    "/backfill-analyses",
    response_model=BackfillResponse,
    dependencies=[Depends(require_bearer)],
)
async def backfill_analyses(
    body: BackfillRequest,
    request: Request,
) -> BackfillResponse:
    """Idempotent: insert missing positions and analyses rows for the given games.

    BBF-21: two-phase.
      Phase 0: walk every game's PGN (CPU-bound) and check existing
               analyses — pure read, no writes, no analysis.
      Phase 1: ONE big asyncio.gather() of stockfish analyses across
               ALL games' missing plies — the actual bottleneck, fully
               parallel across the pool's N slots (BBF-19).
      Phase 2: per-game INSERTs of positions then analyses, in small
               transactions. Preserves FK ordering (positions.id must
               exist before analyses.position_id) and keeps each
               transaction small so SQLite write-lock contention stays
               low.
    """
    from chess_coach.protocol_types.analysis import AnalysisRequest

    db_path = _db_path(request)
    pool = _engine_pool(request)
    games_processed = 0
    games_skipped_no_pgn = 0
    plies_analyzed = 0
    plies_skipped_existing = 0
    positions_inserted = 0
    failures = 0

    # game_plans: per-game state carried from Phase 0 to Phase 2.
    #   plan["missing_plies"]: list of (ply_idx, fen) needing analysis
    #   plan["positions"]: full mainline positions (for Phase 2 INSERTs)
    # Phase 1's results are stored separately, keyed by (plan_index, ply_idx).
    game_plans: list[dict[str, Any]] = []
    # (plan_index, ply_idx) -> AnalysisResult or Exception
    analysis_results: dict[tuple[int, int], Any] = {}

    # ── Phase 0: load games, walk PGNs, find missing plies. ──
    async with aiosqlite.connect(db_path) as db:
        if body.game_ids:
            placeholders = ",".join("?" for _ in body.game_ids)
            cur = await db.execute(
                f"SELECT id, pgn_raw FROM games WHERE id IN ({placeholders})",
                body.game_ids,
            )
        else:
            cur = await db.execute(
                "SELECT id, pgn_raw FROM games "
                "WHERE pgn_raw IS NOT NULL AND pgn_raw != ''"
            )
        rows = list(await cur.fetchall())

        for game_id, pgn_raw in rows:
            if not pgn_raw:
                games_skipped_no_pgn += 1
                continue
            positions = _walk_game_mainline(pgn_raw, body.max_plies)
            if positions is None or not positions:
                games_skipped_no_pgn += 1
                continue
            existing_ids = await _existing_analysis_ids(db, game_id)
            missing_plies: list[tuple[int, str]] = []
            for ply_idx, fen, _uci, _san in positions:
                analysis_id = f"{game_id}:{ply_idx}:stockfish:{body.depth}"
                if analysis_id in existing_ids:
                    plies_skipped_existing += 1
                else:
                    missing_plies.append((ply_idx, fen))
            # Always record the plan; even when missing_plies is empty
            # we still need to insert positions in Phase 2.
            game_plans.append({
                "game_id": game_id,
                "positions": positions,
                "missing_plies": missing_plies,
            })

    # ── Phase 1: ONE big gather of stockfish analyses across all games. ──
    # The slow part. Pool's semaphore caps concurrency to N (BBF-19).
    tasks: list[tuple[int, int, str]] = []
    for plan_idx, plan in enumerate(game_plans):
        for ply_idx, fen in plan["missing_plies"]:
            tasks.append((plan_idx, ply_idx, fen))

    if tasks:
        coros = [
            _analyze_one(pool, AnalysisRequest, fen, body.depth)
            for _plan_idx, _ply_idx, fen in tasks
        ]
        gathered = await asyncio.gather(*coros, return_exceptions=True)
        for (plan_idx, ply_idx, _fen), result in zip(tasks, gathered):
            analysis_results[(plan_idx, ply_idx)] = result

    # ── Phase 2: per-game INSERTs in small transactions. ──
    async with aiosqlite.connect(db_path) as db:
        for plan_idx, plan in enumerate(game_plans):
            game_id = plan["game_id"]
            positions = plan["positions"]

            # Positions first (FK: analyses.position_id REFERENCES positions.id).
            prev_id: str | None = None
            for ply_idx, fen, move_uci, move_san in positions:
                position_id = f"{game_id}:{ply_idx}"
                ok = await _insert_position(
                    db, position_id, game_id, prev_id,
                    ply_idx, fen, move_uci, move_san,
                )
                if ok:
                    positions_inserted += 1
                prev_id = position_id

            # Then analyses, for plies that were analyzed in Phase 1.
            for ply_idx, _fen in plan["missing_plies"]:
                result = analysis_results.get((plan_idx, ply_idx))
                if result is None:
                    # Should not happen — missing_plies was the gather list.
                    continue
                if isinstance(result, Exception):
                    logger.warning(
                        "backfill %s ply %d: analyze failed: %s",
                        game_id, ply_idx, result,
                    )
                    failures += 1
                    continue
                position_id = f"{game_id}:{ply_idx}"
                ok = await _insert_analysis(db, position_id, body.depth, result)
                if ok:
                    plies_analyzed += 1
                # else: INSERT OR IGNORE returned rowcount 0 — duplicate,
                # not a failure; the analysis is present.

            await db.commit()
            games_processed += 1

    return BackfillResponse(
        games_processed=games_processed,
        games_skipped_no_pgn=games_skipped_no_pgn,
        plies_analyzed=plies_analyzed,
        plies_skipped_existing=plies_skipped_existing,
        positions_inserted=positions_inserted,
        failures=failures,
    )
