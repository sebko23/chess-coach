"""Qdrant vector store wrapper for kb pipeline.

Uses in-memory Qdrant by default. Pass persist_path to persist to disk.
When Docker Compose adds a Qdrant container, swap the client instantiation
to QdrantClient(host="localhost", port=6333) and remove the in-memory flag.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

COLLECTION = "positions"


@dataclass
class SearchResult:
    fen: str
    ply: int
    game_id: str
    score: float


class PositionStore:
    """Thin wrapper around a Qdrant collection for chess positions."""

    def __init__(
        self,
        persist_path: str | None = None,
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
    ) -> None:
        if qdrant_url and qdrant_url != ":memory:":
            self._client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key or None)
            logger.info("PositionStore: connecting to persistent Qdrant at %s", qdrant_url)
        elif persist_path:
            self._client = QdrantClient(path=persist_path)
            logger.info("PositionStore: persisting to %s", persist_path)
        else:
            self._client = QdrantClient(":memory:")
            logger.info("PositionStore: using in-memory Qdrant")
        self._dim: int | None = None

    def _ensure_collection(self, dim: int) -> None:
        if self._dim == dim:
            return
        existing = [c.name for c in self._client.get_collections().collections]
        if COLLECTION in existing:
            self._client.delete_collection(COLLECTION)
        self._client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        self._dim = dim
        logger.info("PositionStore: created collection dim=%d", dim)

    def insert(
        self,
        fens: list[str],
        vectors: np.ndarray,
        plies: list[int],
        game_ids: list[str],
    ) -> None:
        """Insert position vectors with metadata."""
        assert len(fens) == len(vectors) == len(plies) == len(game_ids)
        self._ensure_collection(vectors.shape[1])
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vectors[i].tolist(),
                payload={"fen": fens[i], "ply": plies[i], "game_id": game_ids[i]},
            )
            for i in range(len(fens))
        ]
        _CHUNK = 1000  # Qdrant default JSON payload limit is 32 MiB; 1k points ~8 MB leaves headroom
        for _start in range(0, len(points), _CHUNK):
            _chunk = points[_start : _start + _CHUNK]
            self._client.upsert(collection_name=COLLECTION, points=_chunk)
        logger.info("PositionStore: inserted %d positions", len(points))

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        """Return top_k most similar positions to the query vector."""
        if self._dim is None:
            return []
        resp = self._client.query_points(
            collection_name=COLLECTION,
            query=query_vector.tolist(),
            limit=top_k,
        )
        hits = resp.points
        return [
            SearchResult(
                fen=h.payload["fen"],
                ply=h.payload["ply"],
                game_id=h.payload["game_id"],
                score=h.score,
            )
            for h in hits
        ]

    def count(self) -> int:
        """Return number of indexed positions."""
        if self._dim is None:
            return 0
        return self._client.count(collection_name=COLLECTION).count
