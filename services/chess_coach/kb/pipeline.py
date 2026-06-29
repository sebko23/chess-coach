"""Memory KB pipeline — index positions and query similar ones.

Entry points:
    index_positions(db_path, limit) — index positions from SQLite into Qdrant
    query_similar(fen, top_k)       — find similar positions by FEN

These are the functions called by the narration pipeline and future KB agent.
The store is module-level so it survives across requests within a process lifetime.
For multi-process deployments, replace with a persistent Qdrant path or container.
"""
from __future__ import annotations

import logging
import sqlite3

from .embedder import embed_one, fit_and_embed
from .store import PositionStore, SearchResult

logger = logging.getLogger(__name__)

_store: PositionStore | None = None


def _get_store() -> PositionStore:
    global _store
    if _store is None:
        _store = PositionStore()
    return _store


def index_positions(
    db_path: str,
    limit: int = 5000,
    persist_path: str | None = None,
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
) -> int:
    """Pull positions from SQLite, embed, and insert into Qdrant.

    Returns the number of positions indexed.
    Safe to call multiple times — recreates the collection on each call.
    Pass qdrant_url to use a persistent Qdrant instance; omit for in-memory.
    """
    global _store
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT p.fen, p.ply, p.game_id
        FROM positions p
        WHERE p.ply BETWEEN 4 AND 40
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()

    if not rows:
        logger.warning("index_positions: no positions found in %s", db_path)
        return 0

    fens = [r[0] for r in rows]
    plies = [r[1] for r in rows]
    game_ids = [r[2] for r in rows]

    # Skip re-embedding if Qdrant already has a populated collection.
    # PositionStore._ensure_collection will reuse it if dim and count match.
    _probe = PositionStore(
        persist_path=persist_path,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
    )
    if _probe.count() >= limit:
        logger.info(
            "index_positions: Qdrant already has %d positions — skipping re-embed",
            _probe.count(),
        )
        _store = _probe
        return _probe.count()
    logger.info("index_positions: embedding %d positions", len(fens))
    vectors = fit_and_embed(fens)

    _store = PositionStore(
        persist_path=persist_path,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
    )
    _store.insert(fens, vectors, plies, game_ids)
    logger.info("index_positions: indexed %d positions", len(fens))
    return len(fens)


def query_similar(fen: str, top_k: int = 5) -> list[SearchResult]:
    """Return top_k positions similar to the given FEN.

    Requires index_positions() to have been called first.
    Returns empty list if the store is not yet indexed.
    """
    store = _get_store()
    if store.count() == 0:
        logger.warning("query_similar: store not indexed — call index_positions first")
        return []
    try:
        vec = embed_one(fen)
        return store.search(vec, top_k=top_k)
    except RuntimeError as exc:
        logger.warning("query_similar: embedder not ready: %s", exc)
        return []
