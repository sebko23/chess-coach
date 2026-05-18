"""Route — POST /v1/narration/explain.

Uses FastAPI dependency injection for the engine pool and narration pipeline
so that route handlers are testable without module-level patching.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request

from chess_coach.protocol_types.narration import NarrationRequest, NarrationResponse
from chess_coach.narration import NarrationPipeline
from chess_coach.engine_orch.pool import EnginePool, AnalysisRequest
from chess_coach.gateway.auth import require_bearer

router = APIRouter(tags=["narration"], dependencies=[Depends(require_bearer)])


async def _get_engine_pool(request: Request) -> EnginePool:
    """Dependency: retrieve the engine pool from app state."""
    pool = request.app.state.engine_pool  # type: ignore[attr-defined]
    if pool is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Engine pool not ready")
    return pool


async def _get_narration_pipeline(request: Request) -> NarrationPipeline:
    """Dependency: retrieve the narration pipeline from app state."""
    pipeline = getattr(request.app.state, "narration_pipeline", None)
    if pipeline is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Narration pipeline not ready")
    return pipeline


@router.post("/v1/narration/explain", response_model=NarrationResponse)
async def explain_position(
    body: NarrationRequest,
    engine_pool: EnginePool = Depends(_get_engine_pool),
    narration_pipeline: NarrationPipeline = Depends(_get_narration_pipeline),
) -> NarrationResponse:
    """Analyse a position and return grounded coaching narration."""
    result = await engine_pool.analyze(
        AnalysisRequest(
            fen=body.fen,
            depth=body.depth,
            multipv=body.multipv,
        ),
        engine_id=body.engine_id,
    )
    narration = await narration_pipeline.explain(result)

    # Build compact response for the frontend
    best_pv = result.pvs[0]
    if best_pv.score.kind == "mate":
        score_display = f"mate in {best_pv.score.value}"
    else:
        score_display = f"{best_pv.score.value / 100:+.2f}"

    # Convert best move to SAN for display
    try:
        import chess
        board = chess.Board(result.fen)
        best_move_san = board.san(chess.Move.from_uci(best_pv.moves[0]))
    except Exception:
        best_move_san = best_pv.moves[0]  # fallback to UCI

    return NarrationResponse(
        fen=result.fen,
        narration=narration,
        depth_reached=result.depth_reached,
        best_move=best_move_san,
        score_display=score_display,
        pv_moves=best_pv.moves,
    )
