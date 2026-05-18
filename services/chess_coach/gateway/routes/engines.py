"""Engine management routes.

Protocol §4.5:
  GET /v1/engines           — list installed engines
  GET /v1/engines/{id}       — engine details + capabilities
  POST /v1/engines/{id}/analyze — start analysis job (delegates to engine pool)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from chess_coach.engine_orch.pool import EnginePool
from chess_coach.errors.codes import ErrorCode
from chess_coach.protocol_types.analysis import AnalysisRequest, AnalysisResult
from chess_coach.gateway.auth import require_bearer

router = APIRouter(tags=["engines"], dependencies=[Depends(require_bearer)])


def _pool(request: Request) -> EnginePool:
    pool = request.app.state.engine_pool  # type: ignore[attr-defined]
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail={"code": ErrorCode.SERVER_UNAVAILABLE.value, "message": "Engine pool not initialised"},
        )
    return pool


@router.get("/v1/engines")
async def list_engines(pool: EnginePool = Depends(_pool)):
    ids = list(pool._specs.keys())
    return {"data": {"engine_ids": ids}}


@router.get("/v1/engines/{engine_id}")
async def engine_info(engine_id: str, pool: EnginePool = Depends(_pool)):
    try:
        info = await pool.engine_info(engine_id)
        return {"data": info}
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.NOT_FOUND.value, "message": f"Engine {engine_id} not found"},
        )


@router.post("/v1/engines/{engine_id}/analyze")
async def analyze_position(
    engine_id: str,
    body: AnalysisRequest,
    request: Request,
    pool: EnginePool = Depends(_pool),
) -> dict[str, Any]:
    try:
        result: AnalysisResult = await pool.analyze(body, engine_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.NOT_FOUND.value, "message": f"Engine {engine_id} not found"},
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=500,
            detail={"code": ErrorCode.INTERNAL.value, "message": str(e)},
        )
    return {"data": result.model_dump()}
