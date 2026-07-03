"""Performance test: forced re-embed round-trip on the live `positions` collection.

Exercises the re-embed branch of ``index_positions()`` (limit > current
points_count) end-to-end: SQL fetch, embed, upsert. Verifies that the
function returns ``min(limit, available_rows_in_ply_window)`` and that
Qdrant grew by exactly that delta. The ``qdrant_snapshot_guard`` fixture
ensures the live collection is restored to its baseline state at teardown,
regardless of pass/fail.

Marker: ``@pytest.mark.perf`` (defined in pyproject.toml; --strict-markers
enforced).
"""
from __future__ import annotations

import sqlite3
import time

import pytest
from qdrant_client import QdrantClient

from chess_coach.kb.pipeline import index_positions


@pytest.mark.perf
def test_forced_reembed_roundtrip(
    qdrant_snapshot_guard: int,
    qdrant_url: str,
    sqlite_db_path: str,
) -> None:
    baseline = qdrant_snapshot_guard
    assert baseline > 0, "baseline points_count must be positive"

    conn = sqlite3.connect(sqlite_db_path)
    try:
        window_rows = conn.execute(
            "SELECT COUNT(*) FROM positions WHERE ply BETWEEN 4 AND 40"
        ).fetchone()[0]
    finally:
        conn.close()

    start = time.monotonic()
    indexed = index_positions(
        sqlite_db_path,
        limit=baseline + 1,
        qdrant_url=qdrant_url,
        qdrant_api_key=None,
    )
    elapsed = time.monotonic() - start

    expected_delta = min(baseline + 1, window_rows)
    assert indexed == expected_delta, (
        f"index_positions returned {indexed}, expected {expected_delta}"
    )

    client = QdrantClient(url=qdrant_url)
    actual_count = client.count(collection_name="positions").count
    assert actual_count == baseline + expected_delta, (
        f"points_count {actual_count} != baseline {baseline} + delta {expected_delta}"
    )

    assert elapsed < 900, f"re-embed took {elapsed:.1f}s, exceeds 900s budget"
