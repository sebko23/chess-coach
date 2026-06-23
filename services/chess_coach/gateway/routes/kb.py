"""Knowledge Base routes — position similarity search.

Routes:
    POST /v1/kb/similar   — find positions similar to a query FEN
    POST /v1/kb/index     — (re)index positions from SQLite
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..auth import require_bearer
from ..route_guard import route_guard
from chess_coach.memory_kb import index_positions, query_similar

logger = logging.getLogger(__name__)

kb_router = APIRouter(prefix="/v1/kb", tags=["kb"])


class SimilarRequest(BaseModel):
    fen: str = Field(..., description="Query FEN to find similar positions for")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results to return")


class SimilarHit(BaseModel):
    rank: int = Field(..., description="Result rank (1 = most similar)")
    fen: str
    ply: int
    game_id: str


class SimilarResponse(BaseModel):
    query_fen: str
    hits: list[SimilarHit]
    kb_ready: bool = Field(
        ...,
        description="False if the KB store has not been indexed yet — hits will be empty",
    )


@kb_router.post(
    "/similar",
    response_model=SimilarResponse,
    dependencies=[Depends(require_bearer)],
)
@route_guard
async def similar_positions(body: SimilarRequest, request: Request) -> SimilarResponse:
    """Return positions from the KB most similar to the query FEN."""
    kb_ready: bool = getattr(request.app.state, "kb_ready", False)
    if not kb_ready:
        logger.warning("kb/similar: KB not ready — returning empty results")
        return SimilarResponse(query_fen=body.fen, hits=[], kb_ready=False)

    results = query_similar(body.fen, top_k=body.top_k)
    hits = [
        SimilarHit(rank=i + 1, fen=r.fen, ply=r.ply, game_id=r.game_id)
        for i, r in enumerate(results)
    ]
    return SimilarResponse(query_fen=body.fen, hits=hits, kb_ready=True)


class IndexRequest(BaseModel):
    limit: int = Field(default=5000, ge=1, le=50000, description="Max positions to index")


@kb_router.post(
    "/index",
    dependencies=[Depends(require_bearer)],
)
@route_guard
async def reindex(body: IndexRequest, request: Request) -> dict[str, str]:
    """Trigger a reindex of the KB from SQLite. Safe to call multiple times."""
    settings = request.app.state.gateway.settings
    db_path = str(settings.sqlite_path)
    qdrant_url = settings.qdrant_url
    qdrant_api_key = settings.qdrant_api_key
    try:
        count = index_positions(
            db_path,
            limit=body.limit,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key,
        )
        request.app.state.kb_ready = True  # type: ignore[attr-defined]
        return {"status": "ok", "indexed": str(count)}
    except Exception as exc:  # noqa: BLE001
        logger.error("kb/index: failed: %s", exc)
        return {"status": "error", "detail": str(exc)}
