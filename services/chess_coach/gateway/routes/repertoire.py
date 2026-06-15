"""Routes for opening repertoire — tree, gaps, novelties."""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Query, Depends, Request
from pydantic import BaseModel

from chess_coach.gateway.auth import require_bearer

router = APIRouter(tags=["repertoire"], dependencies=[Depends(require_bearer)])


class OpeningNode(BaseModel):
    fen: str
    move_san: str | None = None
    move_uci: str | None = None
    ply: int = 0
    times_played: int = 1
    children_count: int = 0


class TreeResponse(BaseModel):
    player_name: str
    color: str
    node_count: int
    nodes: list[OpeningNode]


class GapItem(BaseModel):
    fen: str
    ply: int
    move_san: str | None = None
    times_reached: int = 0
    suggested_alternatives: list[str] = []


class NoveltyItem(BaseModel):
    fen: str
    ply: int
    move_san: str | None = None
    game_id: str = ""
    total_times_played: int = 0


@router.get("/v1/repertoire/{player}/tree", response_model=TreeResponse)
async def get_repertoire_tree(player: str, request: Request, color: str = Query(default="white", pattern="^(white|black)$")):
    settings = request.app.state.gateway.settings
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, fen, move_san, move_uci, ply FROM positions "
            "WHERE ply BETWEEN 1 AND 12 ORDER BY ply, id LIMIT 500"
        )
        rows = await cur.fetchall()
    nodes = [
        OpeningNode(fen=r["fen"], move_san=r["move_san"], move_uci=r["move_uci"], ply=r["ply"])
        for r in rows
    ]
    return TreeResponse(player_name=player, color=color, node_count=len(nodes), nodes=nodes)


@router.get("/v1/repertoire/{player}/gaps", response_model=list[GapItem])
async def get_repertoire_gaps(player: str, request: Request, color: str = Query(default="white", pattern="^(white|black)$")):
    settings = request.app.state.gateway.settings
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT fen, ply, move_san FROM positions WHERE ply BETWEEN 8 AND 12 LIMIT 20")
        rows = await cur.fetchall()
    return [GapItem(fen=r["fen"], ply=r["ply"], move_san=r["move_san"]) for r in rows]


@router.get("/v1/repertoire/{player}/novelties", response_model=list[NoveltyItem])
async def get_repertoire_novelties(player: str, request: Request, color: str = Query(default="white", pattern="^(white|black)$")):
    return []
