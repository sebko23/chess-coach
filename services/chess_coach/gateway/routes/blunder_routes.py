"""Routes for blunder queries."""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from chess_coach.gateway.auth import require_bearer
from ..route_guard import route_guard

router = APIRouter(tags=["blunders"], dependencies=[Depends(require_bearer)])


class BlunderOut(BaseModel):
    position_id: str
    fen: str
    game_id: str
    ply: int
    score_cp: int | None = None
    classification: str | None = None
    cp_delta: float | None = None




class BlunderEnvelope(BaseModel):
    blunders: list[BlunderOut]




class BatchBlunderRequest(BaseModel):
    fens: list[str]


@router.post("/v1/blunders/batch-by-fen", response_model=dict)
@route_guard
async def get_blunders_batch(body: BatchBlunderRequest, request: Request):
    """Return blunder classifications for multiple FENs in one round trip."""
    settings = request.app.state.gateway.settings
    results: dict[str, str | None] = {}
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        db.row_factory = aiosqlite.Row
        for fen in body.fens:
            cur = await db.execute(
                "SELECT a.classification "
                "FROM positions p "
                "JOIN analyses a ON a.position_id = p.id "
                "WHERE p.fen = ? "
                "AND a.classification IS NOT NULL "
                "ORDER BY ABS(COALESCE(a.cp_delta,0)) DESC LIMIT 1",
                (fen,),
            )
            row = await cur.fetchone()
            results[fen] = row["classification"] if row else None
    return {"results": results}


@router.get("/v1/blunders/by-fen", response_model=BlunderEnvelope)
@route_guard
async def get_blunders_by_fen(fen: str, request: Request, limit: int = 50):
    """Return blunders matching a specific FEN."""
    settings = request.app.state.gateway.settings
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT p.id AS position_id, p.fen, p.game_id, p.ply, "
            "a.score_cp, a.classification, a.cp_delta "
            "FROM positions p "
            "JOIN analyses a ON a.position_id = p.id "
            "WHERE p.fen = ? "
            "ORDER BY ABS(COALESCE(a.cp_delta,0)) DESC LIMIT ?",
            (fen, limit),
        )
        rows = await cur.fetchall()
    return BlunderEnvelope(blunders=[dict(r) for r in rows])
