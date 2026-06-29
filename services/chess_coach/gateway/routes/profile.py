"""Player profile / statistics routes."""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from chess_coach.gateway.auth import require_bearer
from ..route_guard import route_guard

router = APIRouter(tags=["profile"], dependencies=[Depends(require_bearer)])


class ProfileStats(BaseModel):
    player_name: str
    total_games: int
    wins: int
    losses: int
    draws: int
    total_analyses: int
    blunder_count: int
    training_cards_due: int


@router.get("/v1/profile/{player}", response_model=ProfileStats)
@route_guard
async def get_profile(player: str, request: Request):
    """Aggregated statistics for a player."""
    settings = request.app.state.gateway.settings
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        db.row_factory = aiosqlite.Row

        cur = await db.execute(
            "SELECT COUNT(*) FROM games WHERE white = ? OR black = ?", (player, player)
        )
        total_games = (await cur.fetchone())[0]

        result_rows = await db.execute_fetchall(
            "SELECT result, COUNT(*) as cnt FROM games "
            "WHERE (white = ? OR black = ?) GROUP BY result",
            (player, player),
        )
        wins = sum(r[1] for r in result_rows if r[0] == "1-0")
        losses = sum(r[1] for r in result_rows if r[0] == "0-1")
        draws = sum(r[1] for r in result_rows if r[0] == "1/2-1/2")

        cur = await db.execute("SELECT COUNT(*) FROM analyses")
        total_analyses = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT COUNT(*) FROM analyses "
            "WHERE classification LIKE '%blunder%' OR ABS(COALESCE(cp_delta,0)) > 150"
        )
        blunder_count = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT COUNT(*) FROM training_cards "
            "WHERE player_name = ? AND due <= strftime('%Y-%m-%dT%H:%M:%fZ','now')",
            (player,),
        )
        training_cards_due = (await cur.fetchone())[0]

    return ProfileStats(
        player_name=player,
        total_games=total_games,
        wins=wins,
        losses=losses,
        draws=draws,
        total_analyses=total_analyses,
        blunder_count=blunder_count,
        training_cards_due=training_cards_due,
    )
