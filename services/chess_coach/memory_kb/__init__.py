"""Memory Knowledge Base — position similarity search via Qdrant + TF-IDF.

Public API:
    index_positions(db_path, limit, persist_path) -> int
    query_similar(fen, top_k) -> list[SearchResult]

See pipeline.py for implementation details.
See embedder.py for the TF-IDF embedder and neural upgrade path.
"""
from .pipeline import index_positions, query_similar
from .store import SearchResult

__all__ = ["index_positions", "query_similar", "SearchResult"]
