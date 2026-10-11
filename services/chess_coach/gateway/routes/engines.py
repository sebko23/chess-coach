"""Engine management routes.

Protocol §4.5:
  GET /v1/engines           — list installed engines
  GET /v1/engines/{id}       — engine details + capabilities
  POST /v1/engines/{id}/analyze — start analysis job (delegates to engine pool)
"""
# ruff: noqa: B008  -- FastAPI Depends() in argument defaults is the intended pattern; flagged uniformly across all route handlers.
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from chess_coach.engine_orch.pool import EnginePool
from chess_coach.gateway.engine_availability import require_engine_available
from chess_coach.errors.codes import ErrorCode
from chess_coach.gateway.auth import require_bearer
from chess_coach.protocol_types.analysis import AnalysisRequest, AnalysisResult

from ..route_guard import route_guard

router = APIRouter(tags=["engines"], dependencies=[Depends(require_bearer)])


def _pool(request: Request) -> EnginePool:
    pool = request.app.state.engine_pool  # type: ignore[attr-defined]
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": ErrorCode.SERVER_UNAVAILABLE.value,
                "message": "Engine pool not initialised",
            },
        )
    return pool


@router.get("/v1/engines")
@route_guard
async def list_engines(pool: EnginePool = Depends(_pool)):
    ids = list(pool._specs.keys())
    return {"data": {"engine_ids": ids}}


@router.get("/v1/engines/{engine_id}")
@route_guard
async def engine_info(engine_id: str, pool: EnginePool = Depends(_pool)):
    # Phase 8 BBF-2 Finding B: preserve 404 vs 503 contract.
    # Unknown engine_id (not in pool._specs) → 404, not 503.
    # require_engine_available() alone would collapse both cases
    # into 503 because is_available() returns False for unknown ids.
    if not pool.is_registered(engine_id):
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.NOT_FOUND.value, "message": f"engine {engine_id} not registered"},
        )
    # Phase 8 BBF-2 Fix 3 Part B: return 503 if the engine was never
    # acquired (e.g., Stockfish binary missing at warmup).
    require_engine_available(pool, engine_id)
    try:
        info = await pool.engine_info(engine_id)
        return {"data": info}
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.NOT_FOUND.value, "message": f"Engine {engine_id} not found"},
        ) from None


@router.post("/v1/engines/{engine_id}/analyze")
@route_guard
async def analyze_position(
    engine_id: str,
    body: AnalysisRequest,
    request: Request,
    pool: EnginePool = Depends(_pool),
) -> dict[str, Any]:
    # Phase 8 BBF-2 Finding B: preserve 404 vs 503 contract.
    # Unknown engine_id (not in pool._specs) → 404, not 503.
    # require_engine_available() alone would collapse both cases
    # into 503 because is_available() returns False for unknown ids.
    # Mirrors the check in engine_info() above so both engine-consuming
    # routes that take engine_id from a path parameter return 404 for
    # unregistered ids before the 503 availability gate fires.
    if not pool.is_registered(engine_id):
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.NOT_FOUND.value, "message": f"engine {engine_id} not registered"},
        )
    # Phase 8 BBF-2 Fix 3 Part B: return 503 if the engine was never
    # acquired (e.g., Stockfish binary missing at warmup).
    require_engine_available(pool, engine_id)
    try:
        result: AnalysisResult = await pool.analyze(body, engine_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.NOT_FOUND.value, "message": f"Engine {engine_id} not found"},
        ) from None
    except RuntimeError as e:
        raise HTTPException(
            status_code=500,
            detail={"code": ErrorCode.INTERNAL.value, "message": str(e)},
        ) from e
    return {"data": result.model_dump()}
