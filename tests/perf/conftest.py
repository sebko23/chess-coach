"""Shared pytest fixtures for performance/live tests under tests/perf/.

These tests need a real, live Qdrant collection and a real SQLite DB -- they
deliberately bypass the top-level tests/conftest.py autouse _isolate_env
fixture, which would otherwise force a private tmp_path data dir and strip
CHESS_COACH_* env vars. The kb module's ``index_positions()`` accepts both
db_path and qdrant_url as explicit args, so the test never consults env
vars in the first place.

Marker convention: tests in this directory must carry ``@pytest.mark.perf``
(defined in pyproject.toml). The --strict-markers addopts means a test
with no marker will be rejected.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import SnapshotPriority

QDRANT_URL = "http://localhost:6333"
SQLITE_DB_PATH = "/root/.local/share/chess-coach/sqlite/chess_coach.db"
COLLECTION = "positions"


@pytest.fixture
def qdrant_url() -> str:
    """Live Qdrant URL. Override locally by parametrizing the test."""
    return QDRANT_URL


@pytest.fixture
def sqlite_db_path() -> str:
    """Live SQLite DB path. Override locally by parametrizing the test."""
    return SQLITE_DB_PATH


@pytest.fixture
def qdrant_snapshot_guard(qdrant_url: str) -> Iterator[int]:
    """Snapshot the live `positions` collection before the test, restore + delete on teardown.

    Yields the baseline ``points_count`` (so tests can use it as a known
    reference value without re-counting). On teardown, recovers from the
    snapshot with ``priority=SnapshotPriority.SNAPSHOT`` (forces snapshot
    data to override the post-test state) and then deletes the snapshot.

    The snapshot creation happens BEFORE the try/finally so that a failed
    ``create_snapshot`` propagates cleanly without triggering a doomed
    restore attempt against a non-existent snapshot. The QdrantClient is
    closed at the end of teardown to release the connection.
    """
    client = QdrantClient(url=qdrant_url)
    baseline_count = client.count(collection_name=COLLECTION).count
    snap = client.create_snapshot(collection_name=COLLECTION)
    snap_path = (
        f"/a0/usr/projects/chess_coach/data/qdrant/snapshots/"
        f"{COLLECTION}/{snap.name}"
    )
    try:
        yield baseline_count
    finally:
        client.recover_snapshot(
            collection_name=COLLECTION,
            location=f"file://{snap_path}",
            priority=SnapshotPriority.SNAPSHOT,
        )
        client.delete_snapshot(
            collection_name=COLLECTION,
            snapshot_name=snap.name,
        )
        client.close()
