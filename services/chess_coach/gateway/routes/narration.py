"""Route — POST /v1/narration/explain."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException

from chess_coach.narration import NarrationPipeline
from chess_coach.engine_orch.pool import EnginePool, AnalysisRequest
from chess_coach.gateway.auth import require_bearer

router = APIRouter(tags=["narration"], dependencies=[Depends(require_bearer)])

# ── injected at startup ───────────────────────────────────────────
_engine_pool: EnginePool | None = None
_narration: NarrationPipeline | None = None


def set_engine_pool(pool: EnginePool) -> None:
    global _engine_pool
    _engine_pool = pool


def set_narration_pipeline(pipeline: NarrationPipeline) -> None:
    global _narration
    _narration = pipeline


@router.post("/narration/explain")
async def explain_position(body: dict) -> dict:
    """Analyse a position and return grounded coaching narration."""
    fen = body.get("fen", "")
    if not fen:
        raise HTTPException(status_code=422, detail="fen is required")
    depth = body.get("depth", 12)
    engine_id = body.get("engine_id", "sf")

    if _engine_pool is None:
        raise HTTPException(status_code=503, detail="Engine pool not ready")
    if _narration is None:
        raise HTTPException(status_code=503, detail="Narration pipeline not ready")

    result = await _engine_pool.analyze(
        AnalysisRequest(fen=fen, depth=depth),
        engine_id=engine_id,
    )
    narration = await _narration.explain(result)
    return {"data": {
        "narration": narration,
        "analysis": result.model_dump(),
    }}
