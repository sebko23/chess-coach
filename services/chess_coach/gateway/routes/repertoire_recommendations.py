"""Repertoire recommendations — engine-powered gap analysis.

POST /v1/repertoire/{player}/recommendations
Reads gap positions (ply 6-16, never played by player) and runs Stockfish depth 14
to suggest the best move for each. Returns ranked by urgency.
"""
from __future__ import annotations

import logging
from typing import Literal

import aiosqlite
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from chess_coach.engine_orch.pool import EnginePool
from chess_coach.protocol_types.analysis import AnalysisRequest
from ..auth import require_bearer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/repertoire", tags=["repertoire"])


def _pool(request: Request) -> EnginePool:
    return request.app.state.engine_pool


def _db_path(request: Request) -> str:
    return str(request.app.state.gateway.settings.sqlite_path)


class RecommendationItem(BaseModel):
    fen: str
    ply: int
    priority: Literal["critical", "important", "normal"]
    best_move_uci: str | None
    best_move_san: str | None
    score_cp: int | None
    depth_reached: int
    alternatives_uci: list[str]
    alternatives_san: list[str]


class RecommendationsResponse(BaseModel):
    player_name: str
    color: str
    total_gaps: int
    recommendations: list[RecommendationItem]


def _priority(score_cp: int | None) -> Literal["critical", "important", "normal"]:
    if score_cp is None:
        return "normal"
    # score from White's perspective; large positive means White is winning
    if abs(score_cp) >= 150:
        return "critical"
    if abs(score_cp) >= 100:
        return "important"
    return "normal"


def _fen_to_color(fen: str) -> str:
    """Return 'white' or 'black' depending on whose turn it is."""
    parts = fen.split()
    return "white" if len(parts) > 1 and parts[1] == "w" else "black"


def _uci_to_san(fen: str, uci: str) -> str:
    """Convert a UCI move (e.g. 'e2e4') to SAN (e.g. 'e4'). Falls back to UCI."""
    try:
        import chess
        board = chess.Board(fen)
        move = chess.Move.from_uci(uci)
        if move in board.legal_moves:
            return board.san(move)
    except Exception:
        pass
    return uci


@router.post(
    "/{player}/recommendations",
    response_model=RecommendationsResponse,
    dependencies=[Depends(require_bearer)],
)
async def get_recommendations(
    player: str,
    color: str = Query("white", pattern="^(white|black)$"),
    limit: int = Query(5, ge=1, le=20),
    engine_id: str = Query("stockfish"),
    pool: EnginePool = Depends(_pool),
    db_path: str = Depends(_db_path),
) -> RecommendationsResponse:
    """Return engine-backed move suggestions for repertoire gaps."""

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if player == "default":
            rows = await db.execute_fetchall(
                """
                SELECT DISTINCT p.fen, p.ply
                FROM positions p
                WHERE p.ply BETWEEN 6 AND 16
                  AND p.fen NOT IN (
                      SELECT DISTINCT fen FROM positions
                      WHERE player_name IS NOT NULL AND player_name != ''
                  )
                ORDER BY p.ply ASC
                LIMIT ?
                """,
                (limit,),
            )
        else:
            rows = await db.execute_fetchall(
                """
                SELECT DISTINCT p.fen, p.ply
                FROM positions p
                WHERE p.player_name = ?
                  AND p.ply BETWEEN 6 AND 16
                  AND p.times_reached = 0
                ORDER BY p.ply ASC
                LIMIT ?
                """,
                (player, limit),
            )

    total_gaps = len(rows)
    recommendations: list[RecommendationItem] = []

    for row in rows:
        fen = row["fen"]
        ply = row["ply"]
        try:
            result = await pool.analyze(
                AnalysisRequest(fen=fen, depth=14, multipv=3),
                engine_id=engine_id,
            )
            best_pv = result.pvs[0] if result.pvs else None
            score_cp = None
            if best_pv and best_pv.score.kind == "cp":
                score_cp = best_pv.score.value
            best_move_uci = best_pv.moves[0] if (best_pv and best_pv.moves) else None
            best_move_san = (
                _uci_to_san(fen, best_move_uci) if best_move_uci else None
            )
            depth_reached = best_pv.depth if best_pv else 14

            alternatives_uci = []
            alternatives_san = []
            for pv in result.pvs[1:]:
                if pv.moves:
                    alt = pv.moves[0]
                    alternatives_uci.append(alt)
                    alternatives_san.append(_uci_to_san(fen, alt))

            recommendations.append(RecommendationItem(
                fen=fen,
                ply=ply,
                priority=_priority(score_cp),
                best_move_uci=best_move_uci,
                best_move_san=best_move_san,
                score_cp=score_cp,
                depth_reached=depth_reached,
                alternatives_uci=alternatives_uci,
                alternatives_san=alternatives_san,
            ))
        except Exception as exc:
            logger.warning("recommendations: analysis failed for fen=%s: %s", fen, exc)
            recommendations.append(RecommendationItem(
                fen=fen,
                ply=ply,
                priority="normal",
                best_move_uci=None,
                best_move_san=None,
                score_cp=None,
                depth_reached=0,
                alternatives_uci=[],
                alternatives_san=[],
            ))

    priority_order = {"critical": 0, "important": 1, "normal": 2}
    recommendations.sort(key=lambda r: priority_order[r.priority])

    return RecommendationsResponse(
        player_name=player,
        color=color,
        total_gaps=total_gaps,
        recommendations=recommendations,
    )
