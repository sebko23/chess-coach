"""Routes for listing and downloading games."""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from chess_coach.errors.codes import ErrorCode
from chess_coach.gateway.auth import require_bearer
from ..route_guard import route_guard

router = APIRouter(tags=["games"], dependencies=[Depends(require_bearer)])


class GameSummary(BaseModel):
    id: str
    white: str | None = None
    black: str | None = None
    date: str | None = None
    event: str | None = None
    result: str | None = None
    import_status: str = "pending"


class GamesListResponse(BaseModel):
    games: list[GameSummary]
    total: int
    limit: int
    offset: int


@router.get("/v1/games", response_model=GamesListResponse)
@route_guard
async def list_games(request: Request, limit: int = 100, offset: int = 0):
    """Return a page of games ordered by creation date descending."""
    settings = request.app.state.gateway.settings
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT COUNT(*) as cnt FROM games")
        total = (await cur.fetchone())["cnt"]
        cur = await db.execute(
            "SELECT id, white, black, date, event, result, import_status "
            "FROM games ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cur.fetchall()
    return GamesListResponse(
        games=[dict(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/v1/games/{game_id}/pgn", response_class=PlainTextResponse)
@route_guard
async def get_game_pgn(game_id: str, request: Request):
    """Return the raw PGN for a game."""
    settings = request.app.state.gateway.settings
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        cur = await db.execute("SELECT pgn_raw FROM games WHERE id = ?", (game_id,))
        row = await cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.NOT_FOUND.value, "message": f"Game {game_id} not found"},
        )
    return PlainTextResponse(row[0], media_type="text/plain")
