"""Routes for per-game evaluation graphs."""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from chess_coach.errors.codes import ErrorCode
from chess_coach.gateway.auth import require_bearer

router = APIRouter(tags=["games"], dependencies=[Depends(require_bearer)])


class EvalPoint(BaseModel):
    ply: int
    score_cp: int | None = None
    score_mate: int | None = None
    move_san: str | None = None
    classification: str | None = None


@router.get("/v1/games/{game_id}/eval-graph", response_model=list[EvalPoint])
async def get_eval_graph(game_id: str, request: Request):
    """Return per-position evaluation scores for a game, ordered by ply."""
    settings = request.app.state.gateway.settings
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT p.ply, a.score_cp, a.score_mate, p.move_san, a.classification "
            "FROM positions p "
            "LEFT JOIN analyses a ON a.position_id = p.id "
            "WHERE p.game_id = ? ORDER BY p.ply ASC",
            (game_id,),
        )
        rows = await cur.fetchall()
    if not rows:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.NOT_FOUND.value, "message": f"No positions found for game {game_id}"},
        )
    return [dict(r) for r in rows]
