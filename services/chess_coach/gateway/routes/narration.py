"""Narration route — LLM-grounded coaching commentary.

POST /v1/narration/explain
Accepts a FEN + optional context (move, eval, game phase) and returns
grounded coaching prose via the narration pipeline.
Stores each narration in the narrations table for audit/replay.
"""
# ruff: noqa: B008  -- FastAPI Depends() in argument defaults is the intended pattern; flagged uniformly across all route handlers.
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import aiosqlite
import pydantic
from fastapi import APIRouter, Depends, Request

from chess_coach.llm_router.router import LLMUnavailableError
from chess_coach.narration.pipeline import (
    NarrationOutput,
    _format_pv_fields,
)
from chess_coach.narration.sanitize import sanitize_user_content
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


def _engine_pool(request: Request):
    """Return the engine pool wired into the gateway app state.

    BBF-87.2: the narration route now invokes engine_pool.analyze()
    to compute a real AnalysisResult (PV + score) when the request
    supplies any engine field (depth / engine_id / multipv).
    The pool is constructed and warmed in gateway/app.py lifespan;
    production code accesses it via this dep so tests can override it.
    """
    return request.app.state.engine_pool


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
    engine_pool=Depends(_engine_pool),
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
        # A-F12 (security-strategy.md §A-F12): the `context` field is
        # user-supplied free-form text and flows into the LLM prompt.
        # Sanitize at the boundary: strip controls / zero-width unicode,
        # cap at 1 KB, wrap in <user_content> delimiters, and detect-flag
        # common injection patterns. The wrapped string is appended to
        # the prompt context exactly as the sanitizer returns it.
        sanitized = sanitize_user_content(
            body.context, source="narration_context",
        )
        context_parts.append(sanitized.text)

    prompt_context = " | ".join(context_parts) if context_parts else "No additional context."

    # BBF-87.2: branch between engine-backed and synthetic narration.
    # When the request supplies any of depth/engine_id/multipv, call
    # engine_pool.analyze() to get a real AnalysisResult with populated
    # PV + score, then feed it through pipeline.explain() so the LLM
    # sees real engine output. When no engine fields are present
    # (backwards-compat with the current GUI call shape), keep the
    # synthetic AnalysisResult path via pipeline.explain_simple().
    wants_engine = (
        body.depth is not None
        or body.engine_id is not None
        or body.multipv is not None
    )
    # Schema default is depth=12 (libs/chess_coach/protocol_types/narration.py:60)
    # and engine_id='stockfish' (:64). Apply those defaults when the
    # caller opts into engine-backed narration but leaves individual
    # fields unset.
    default_depth = 12
    default_engine_id = "stockfish"
    default_multipv = 1
    depth = body.depth if body.depth is not None else default_depth
    engine_id = body.engine_id if body.engine_id is not None else default_engine_id
    multipv = body.multipv if body.multipv is not None else default_multipv
    if wants_engine:
        try:
            from chess_coach.protocol_types.analysis import AnalysisRequest

            analysis = await engine_pool.analyze(
                AnalysisRequest(
                    fen=body.fen,
                    depth=depth,
                    multipv=multipv,
                ),
                engine_id,
            )
            text, corpus_entry_id = await pipeline.explain(analysis)
            pv_moves, score_display = _format_pv_fields(analysis)
            # Pipeline returns (narration_str, corpus_entry_id); wrap
            # into NarrationOutput shape with the real PV from analysis.
            output = NarrationOutput(
                narration=text,
                pv_moves=pv_moves,
                score_display=score_display,
                corpus_entry_id=corpus_entry_id,
            )
            grounded = not output.narration.startswith("Stockfish evaluates this position as")
        except LLMUnavailableError as exc:
            # LLM is unavailable (no API key, network down, OpenRouter 5xx).
            # Synthesize a minimal narration so the client gets *some* text
            # and the UI doesn't break; the absence of <move>/<eval> tags
            # already signals to the renderer that this isn't a real
            # analysis. Engine output is intact; we just couldn't get
            # the LLM to wrap it.
            logger.warning(
                "narration engine-backed path LLM-unavailable for fen=%s: %s",
                body.fen[:20],
                exc,
            )
            output = NarrationOutput(
                narration=f"Position after {body.move_san or 'the last move'}. "
                          f"Evaluation: {body.eval_cp or 0} centipawns.",
                pv_moves=[],
                score_display="",
            )
            grounded = False
        except (ValueError, pydantic.ValidationError) as exc:
            # Malformed request body (invalid FEN, schema drift). Same
            # fallback shape as LLM-unavailable; this is a 4xx-class
            # failure that the route_guard will surface separately.
            logger.warning(
                "narration engine-backed path bad-request for fen=%s: %s",
                body.fen[:20],
                exc,
            )
            output = NarrationOutput(
                narration=f"Position after {body.move_san or 'the last move'}. "
                          f"Evaluation: {body.eval_cp or 0} centipawns.",
                pv_moves=[],
                score_display="",
            )
            grounded = False
        # NOTE: EngineHungError, EngineTimeoutError, RuntimeError, and
        # other unhandled exceptions deliberately PROPAGATE to
        # @route_guard above, producing a 5xx with the ADR-0002 error
        # envelope. Silently fabricating a 200 with fake analysis on
        # a real engine failure was the BBF-87.2 regression this
        # BBF-87.2.1 fixes.
    else:
        # Synthetic path: no engine fields supplied. Keeps the old
        # behaviour where the LLM sees an empty PV. Backwards-compat
        # with the current GUI call shape.
        try:
            output = await pipeline.explain_simple(
                fen=body.fen,
                move_san=body.move_san,
                eval_cp=body.eval_cp,
                game_phase=body.game_phase,
                context=prompt_context,
            )
            grounded = not output.narration.startswith("Stockfish evaluates this position as")
        except LLMUnavailableError as exc:
            logger.warning("narration pipeline LLM-unavailable for fen=%s: %s", body.fen[:20], exc)
            output = NarrationOutput(
                narration=f"Position after {body.move_san or 'the last move'}. "
                          f"Evaluation: {body.eval_cp or 0} centipawns.",
                pv_moves=[],
                score_display="",
            )
            grounded = False
        except (ValueError, pydantic.ValidationError) as exc:
            logger.warning(
                "narration pipeline bad-request for fen=%s: %s",
                body.fen[:20],
                exc,
            )
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
    # BBF-87.2: populate depth_reached + best_move from the real
    # AnalysisResult when engine-backed; None on the synthetic path.
    depth_reached_value = None
    best_move_value = None
    if wants_engine and 'analysis' in locals():
        depth_reached_value = analysis.depth_reached
        best_move_value = (
            analysis.pvs[0].moves[0]
            if analysis.pvs and analysis.pvs[0].moves
            else None
        )

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
        depth_reached=depth_reached_value,
        best_move=best_move_value,
        corpus_entry_id=output.corpus_entry_id,
    )
