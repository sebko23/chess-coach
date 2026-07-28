"""Narration route — LLM-grounded coaching commentary.

POST /v1/narration/explain
Accepts a FEN + optional context (move, eval, game phase) and returns
grounded coaching prose via the narration pipeline.
Stores each narration in the narrations table for audit/replay.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import aiosqlite
from fastapi import APIRouter, Depends, Request

from chess_coach.narration.pipeline import NarrationOutput
from chess_coach.protocol_types.narration import (
    NarrationRequest,
    NarrationResponse,
)

from ..auth import require_bearer
from ..route_guard import route_guard

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/narration", tags=["narration"])


def _db_path(request: Request) -> str:
    return str(request.app.state.gateway.settings.sqlite_path)


def _pipeline(request: Request):
    return request.app.state.narration_pipeline


async def _resolve_position_id(db_path: str, fen: str) -> str:
    """BBF-87.1.y: resolve a real positions.id for the FEN.

    Lookup an existing positions row by FEN; if none exists, insert
    a freeform positions row with game_id=NULL. Returns the id of
    the row.

    Soft semantics: if multiple positions rows exist for the same
    FEN, the first one (by arbitrary SQLite order) is reused. Race
    conditions where two concurrent narrations of the same FEN
    both INSERT a new positions row are tolerated; the duplicate
    is harmless (positions has no UNIQUE constraint on fen).

    BBF-87.1.y: this is the FEN-only path; import-PGN flow
    (services/chess_coach/gateway/routes/pgn_import.py) creates
    positions rows with real game_id values, so this helper's
    game_id=NULL insert is the only FEN-only case in production.
    """
    async with aiosqlite.connect(db_path) as db:
        # Enable FK enforcement on this connection. Python's
        # sqlite3 defaults PRAGMA foreign_keys to OFF, so we must
        # enable it explicitly to get the same behavior as
        # production app code.
        await db.execute("PRAGMA foreign_keys = ON")
        # Look up first; reuse the existing id if any.
        async with db.execute(
            "SELECT id FROM positions WHERE fen = ? LIMIT 1", (fen,)
        ) as cur:
            row = await cur.fetchone()
        if row is not None:
            return row[0]
        # No existing row; insert a freeform positions row.
        new_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO positions (id, game_id, fen, ply, is_mainline)
               VALUES (?, NULL, ?, 0, 1)""",
            (new_id, fen),
        )
        await db.commit()
        return new_id


class NarrationRouteResponse(NarrationResponse):
    """Route-layer response wrapper.

    Embeds the canonical NarrationResponse fields plus route-local audit
    metadata (narration_id, grounded, created_at). The audit fields are
    useful to clients -- the grounded flag drives frontend commentary
    rendering (ungrounded/template outputs render with a different style).
    """
    narration_id: str
    grounded: bool
    created_at: str


@router.post(
    "/explain",
    response_model=NarrationRouteResponse,
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
    now = datetime.now(UTC).isoformat()

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
        grounded = not output.narration.startswith("Stockfish evaluates this position as")
    except Exception as exc:
        logger.warning("narration pipeline failed for fen=%s: %s", body.fen[:20], exc)
        output = NarrationOutput(
            narration=f"Position after {body.move_san or 'the last move'}. "
                      f"Evaluation: {body.eval_cp or 0} centipawns.",
            pv_moves=[],
            score_display="",
        )
        grounded = False

    # BBF-87.1.y: position_id is now a real FK to positions(id).
    # The route resolves a positions row per call: lookup an
    # existing position by FEN, or insert a freeform one with
    # game_id=NULL. The narrations INSERT uses the resolved id.
    # Migration 0009 made positions.game_id nullable; this is
    # the only way the route can insert positions rows without
    # a game context.
    position_id_value = await _resolve_position_id(db_path, body.fen)
    corpus_entry_id_value = output.corpus_entry_id

    # Store in narrations table
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO narrations
               (id, position_id, model, narration, validated, created_at,
                corpus_entry_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                narration_id,
                position_id_value,
                "narration-r1",  # model identifier, configurable later
                output.narration,
                1 if grounded else 0,
                now,
                corpus_entry_id_value,
            ),
        )
        await db.commit()

    return NarrationRouteResponse(
        narration_id=narration_id,
        fen=body.fen,
        narration=output.narration,
        grounded=grounded,
        created_at=now,
        pv_moves=output.pv_moves,
        score_display=output.score_display,
        depth_reached=None,
        best_move=None,
        corpus_entry_id=output.corpus_entry_id,
    )
