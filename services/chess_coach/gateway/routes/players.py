"""Player listing route for player selector dropdown."""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from chess_coach.gateway.auth import require_bearer
from chess_coach.gateway.route_guard import route_guard

router = APIRouter(tags=["players"], dependencies=[Depends(require_bearer)])


class PlayerListResponse(BaseModel):
    players: list[str]


@router.get("/v1/players", response_model=PlayerListResponse)
@route_guard
async def list_players(request: Request):
    """Return all distinct player names from the games table."""
    settings = request.app.state.gateway.settings
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        rows = await db.execute_fetchall(
            """
            SELECT DISTINCT name FROM (
                SELECT white AS name FROM games WHERE white != '?' AND white != ''
                UNION
                SELECT black AS name FROM games WHERE black != '?' AND black != ''
            ) ORDER BY name
            """
        )
        players = [row[0] for row in rows]
    return PlayerListResponse(players=players)
