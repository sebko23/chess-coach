"""Back-fill engine analyses for existing imported games.

POST /v1/import/backfill-analyses
Body: { game_ids?: list[str], depth: int = 8, max_plies: int = 200 }
Returns: { games_processed, games_skipped_no_pgn, plies_analyzed,
           plies_skipped_existing, positions_inserted, failures }

Idempotent: re-running the same request inserts only the missing positions
and analyses rows. Safe to call on a fully-imported corpus; cost is bounded by
`len(game_ids) * max_plies * stockfish_time_per_ply`.
"""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, timezone

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


@router.post(
    "/backfill-analyses",
    response_model=BackfillResponse,
    dependencies=[Depends(require_bearer)],
)
async def _analyze_and_insert(
    db,
    pool,
    AnalysisRequest,
    game_id,
    ply_idx,
    fen,
    depth,
) -> bool:
    position_id = f"{game_id}:{ply_idx}"
    analysis_id = f"{position_id}:stockfish:{depth}"
    try:
        req = AnalysisRequest(fen=fen, depth=depth, engine_id="stockfish")
        result = await pool.analyze(req, "stockfish")
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
        analyses_row = {
            "id": analysis_id,
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
        cols_csv = ", ".join(analyses_row.keys())
        placeholders_sql = ", ".join("?" for _ in analyses_row)
        sql = f"INSERT OR IGNORE INTO analyses ({cols_csv}) VALUES ({placeholders_sql})"
        cur = await db.execute(sql, list(analyses_row.values()))
        return cur.rowcount == 1
    except Exception as exc:
        logger.warning(
            "backfill %s: analyze or insert failed for ply %d: %s",
            game_id, ply_idx, exc,
        )
        return False

async def backfill_analyses(
    body: BackfillRequest,
    request: Request,
) -> BackfillResponse:
    """Idempotent: insert missing positions and analyses rows for the given games."""
    db_path = _db_path(request)
    pool = _engine_pool(request)
    games_processed = 0
    games_skipped_no_pgn = 0
    plies_analyzed = 0
    plies_skipped_existing = 0
    positions_inserted = 0
    failures = 0

    from chess_coach.protocol_types.analysis import AnalysisRequest

    async with aiosqlite.connect(db_path) as db:
        # Select games to process.
        if body.game_ids:
            placeholders = ",".join("?" for _ in body.game_ids)
            cur = await db.execute(
                f"SELECT id, pgn_raw FROM games WHERE id IN ({placeholders})",
                body.game_ids,
            )
        else:
            cur = await db.execute(
                "SELECT id, pgn_raw FROM games WHERE pgn_raw IS NOT NULL AND pgn_raw != ''"
            )
        rows = list(await cur.fetchall())

        for game_id, pgn_raw in rows:
            if not pgn_raw:
                games_skipped_no_pgn += 1
                continue

            # Walk the game's mainline.
            try:
                pgn_io = io.StringIO(pgn_raw)
                game = chess.pgn.read_game(pgn_io)
            except Exception as exc:
                logger.warning("backfill %s: failed to parse PGN: %s", game_id, exc)
                failures += 1
                continue

            if game is None:
                games_skipped_no_pgn += 1
                continue

            # Walk plies 0..max_plies.
            board = game.board()
            positions: list[tuple[int, str, str | None, str | None]] = [
                (0, board.fen(), None, None)
            ]
            ply = 1
            for move in game.mainline_moves():
                if ply > body.max_plies:
                    break
                move_uci = move.uci()
                move_san = board.san(move)
                board.push(move)
                positions.append((ply, board.fen(), move_uci, move_san))
                ply += 1

            # BBF-15b: also back-fill positions. The 33 BBF-7/BBF-8 games
            # were imported before BBF-9 added the positions INSERT, so they
            # have pgn_raw but no positions. The eval-graph join (positions
            # ⨝ analyses) cannot return rows without positions, even when
            # the analyses INSERT succeeds. So we walk the mainline here and
            # INSERT OR IGNORE positions too.
            prev_id: str | None = None
            for ply_idx, fen, move_uci, move_san in positions:
                position_id = f"{game_id}:{ply_idx}"
                try:
                    cur = await db.execute(
                        "INSERT OR IGNORE INTO positions "
                        "(id, game_id, parent_id, fen, move_uci, move_san, ply, is_mainline) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (position_id, game_id, prev_id, fen, move_uci, move_san, ply_idx, 1),
                    )
                    if cur.rowcount == 1:
                        positions_inserted += 1
                except Exception as exc:
                    logger.warning(
                        "backfill %s: positions insert failed for %s: %s",
                        game_id, position_id, exc,
                    )
                prev_id = position_id

            # Read existing analyses ids for this game.
            cur = await db.execute(
                "SELECT a.id FROM analyses a JOIN positions p ON a.position_id = p.id WHERE p.game_id = ?",
                (game_id,),
            )
            existing_ids = {row[0] for row in await cur.fetchall()}

            tasks = [
                _analyze_and_insert(
                    db,
                    pool,
                    AnalysisRequest,
                    game_id,
                    ply_idx,
                    fen,
                    body.depth,
                )
                for ply_idx, fen, _, _ in positions
                if f"{game_id}:{ply_idx}:stockfish:{body.depth}" not in existing_ids
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for ok in results:
                if ok is True:
                    plies_analyzed += 1
                else:
                    if isinstance(ok, Exception):
                        logger.warning(
                            "backfill %s: gather raised: %s", game_id, ok,
                        )
                        failures += 1
                    plies_skipped_existing += 1

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
