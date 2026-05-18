"""Analysis routes.

Protocol §4.6:
  POST /v1/analysis/positions  — simple position analysis (convenience alias)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from chess_coach.engine_orch.pool import EnginePool
from chess_coach.errors.codes import ErrorCode
from chess_coach.protocol_types.analysis import AnalysisRequest
from chess_coach.gateway.auth import require_bearer

router = APIRouter(tags=["analysis"], dependencies=[Depends(require_bearer)])


def _pool_from_request(request: Request) -> EnginePool:
    pool = request.app.state.engine_pool  # type: ignore[attr-defined]
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail={"code": ErrorCode.SERVER_UNAVAILABLE.value, "message": "Engine pool not initialised"},
        )
    return pool


@router.post("/v1/analysis/positions")
async def analyze_position(
    body: dict[str, Any],
    request: Request,
    pool: EnginePool = Depends(_pool_from_request),
) -> dict[str, Any]:
    try:
        req = AnalysisRequest(**body)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail={"code": ErrorCode.VALIDATION_ERROR.value, "message": str(e)},
        )
    engine_id = req.engine_id or "stockfish"
    try:
        result = await pool.analyze(req, engine_id)
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
