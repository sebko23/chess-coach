"""Narration route — LLM-grounded coaching commentary.

POST /v1/narration/explain
Accepts a FEN + optional context (move, eval, game phase) and returns
grounded coaching prose via the narration pipeline.
Stores each narration in the narrations table for audit/replay.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..auth import require_bearer
from ..route_guard import route_guard
from chess_coach.narration.pipeline import NarrationOutput

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/narration", tags=["narration"])


def _db_path(request: Request) -> str:
    return str(request.app.state.gateway.settings.sqlite_path)


def _pipeline(request: Request):
    return request.app.state.narration_pipeline


class NarrationRequest(BaseModel):
    fen: str
    move_san: str | None = None
    move_uci: str | None = None
    eval_cp: int | None = None
    game_phase: str | None = None  # "opening" | "middlegame" | "endgame"
    player_name: str | None = None
    context: str | None = None  # free-form extra context


class NarrationResponse(BaseModel):
    narration_id: str
    fen: str
    text: str
    grounded: bool
    created_at: str
    pv_moves: list[str] | None = None
    score_display: str | None = None


@router.post(
    "/explain",
    response_model=NarrationResponse,
    dependencies=[Depends(require_bearer)],
)
@route_guard
async def explain_position(
    body: NarrationRequest,
    db_path: str = Depends(_db_path),
    pipeline=Depends(_pipeline),
) -> NarrationResponse:
    """Generate grounded coaching commentary for a chess position."""
    narration_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Build prompt context
    context_parts = []
    if body.move_san:
        context_parts.append(f"Move played: {body.move_san}")
    if body.eval_cp is not None:
        side = "+" if body.eval_cp >= 0 else ""
        context_parts.append(f"Evaluation: {side}{body.eval_cp/100:.2f}")
    if body.game_phase:
        context_parts.append(f"Phase: {body.game_phase}")
    if body.context:
        context_parts.append(body.context)

    prompt_context = " | ".join(context_parts) if context_parts else "No additional context."

    # Call narration pipeline
    try:
        output = await pipeline.explain_simple(
            fen=body.fen,
            move_san=body.move_san,
            eval_cp=body.eval_cp,
            game_phase=body.game_phase,
            context=prompt_context,
        )
        # Template fallback prefix from pipeline._template_fallback()
        grounded = not output.text.startswith("Stockfish evaluates this position as")
    except Exception as exc:
        logger.warning("narration pipeline failed for fen=%s: %s", body.fen[:20], exc)
        output = NarrationOutput(
            text=f"Position after {body.move_san or 'the last move'}. "
                 f"Evaluation: {body.eval_cp or 0} centipawns.",
            pv_moves=[],
            score_display="",
        )
        grounded = False

    # Store in narrations table
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO narrations
               (id, position_id, model, narration, validated, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                narration_id,
                body.fen,
                "narration-r1",  # model identifier, configurable later
                output.text,
                1 if grounded else 0,
                now,
            ),
        )
        await db.commit()

    return NarrationResponse(
        narration_id=narration_id,
        fen=body.fen,
        text=output.text,
        grounded=grounded,
        created_at=now,
        pv_moves=output.pv_moves,
        score_display=output.score_display,
    )
