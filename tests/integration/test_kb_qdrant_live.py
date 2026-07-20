"""Live integration test: KB routes against a real Qdrant sidecar.

Marked `@pytest.mark.integration` -- skipped unless the new
qdrant-smoke CI job explicitly enables it (see BBF-52's smoke.yml
changes). This test exercises the sidecar code path
(`QdrantClient(url=qdrant_url)`) end-to-end: a real gateway app
with lifespan, real /v1/kb/index and /v1/kb/similar routes, and
a live Qdrant at CHESS_COACH_QDRANT_URL (set by the qdrant-smoke
job to http://127.0.0.1:6333).

Why live and not mocked: the persistent-path unit test in
tests/unit/test_kb_persistent_path.py exercises the
`QdrantClient(path=...)` branch. This test exercises the
`QdrantClient(url=...)` branch -- the production BBF-52 path --
which is the whole point of BBF-52. A mock would just be testing
the mock.

BBF-53: rewritten to use the new tests/integration/conftest.py
fixtures. The old version tried to instantiate GatewaySettings()
directly, but the top-level tests/conftest.py's `_isolate_env`
autouse fixture had already stripped CHESS_COACH_QDRANT_URL from
the env by then -- so the settings came back with qdrant_url=
":memory:" and the test's assertion failed. The new conftest
re-installs the env var from os.environ after _isolate_env runs.

Requires:
  - A live Qdrant at CHESS_COACH_QDRANT_URL (qdrant-smoke job starts
    one via `docker run -d --name qdrant-ci -p 6333:6333
    qdrant/qdrant:v1.12.4`).
  - The gateway app started with that env var set so settings.qdrant_url
    is not the :memory: default.
"""
from __future__ import annotations

import os
import sqlite3

import pytest

from chess_coach.gateway.auth import set_active_token

pytestmark = pytest.mark.integration


def _qdrant_url_set() -> bool:
    """Skip when the env var is unset (e.g. local unit test run)."""
    url = os.environ.get("CHESS_COACH_QDRANT_URL", "")
    return bool(url) and url != ":memory:"


# Note: this skipif is checked AT TEST COLLECTION time, before
# fixtures run. The integration conftest's _restore_qdrant_env
# runs AFTER this check, so if CHESS_COACH_QDRANT_URL is unset
# in the parent process env (typical local dev), the test
# skips cleanly. In CI, the pytest CLI is invoked with the env
# var set in the env: block of the workflow step.
pytestmark = pytest.mark.skipif(
    not _qdrant_url_set(),
    reason="CHESS_COACH_QDRANT_URL is unset or :memory:; live Qdrant not available",
)


def test_qdrant_sqlite_fixture_matches_gateway_path(
    settings, qdrant_sqlite_path
) -> None:
    """The integration settings must point at the populated deterministic DB."""
    assert settings.sqlite_path == qdrant_sqlite_path
    assert settings.qdrant_url == "http://127.0.0.1:6333"
    with sqlite3.connect(qdrant_sqlite_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM positions WHERE ply BETWEEN 4 AND 40"
        ).fetchone()[0]
    assert count == 5


async def test_index_and_query_against_live_qdrant(client):
    """End-to-end: POST /v1/kb/index, then POST /v1/kb/similar.

    The gateway's index_positions() connects to the live Qdrant,
    creates a collection, upserts vectors. We then query a FEN
    that is in the corpus and assert a non-empty hit list.

    The embedder is a required runtime dependency in this CI job.
    Any index error is a hard failure; skipping would turn a broken
    end-to-end path into a green workflow.
    """

    set_active_token("devtoken123")
    headers = {"Authorization": "Bearer devtoken123"}

    # Trigger (re)index. Small limit keeps the test fast.
    idx_resp = await client.post(
        "/v1/kb/index",
        json={"limit": 5},
        headers=headers,
    )
    assert idx_resp.status_code == 200, idx_resp.text
    body = idx_resp.json()
    assert body["status"] == "ok", body

    indexed = int(body["indexed"])
    assert indexed > 0, "index returned 0 positions"

    # Query a known opening FEN that is likely in the corpus
    # (positions with ply between 4 and 40 are indexed, per
    # pipeline.py:50).
    query_fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    sim_resp = await client.post(
        "/v1/kb/similar",
        json={"fen": query_fen, "top_k": 3},
        headers=headers,
    )
    assert sim_resp.status_code == 200, sim_resp.text
    sim_body = sim_resp.json()
    assert sim_body["kb_ready"] is True
    # Should get at least 1 hit (the index call returned > 0).
    assert len(sim_body["hits"]) >= 1
    assert sim_body["hits"][0]["rank"] == 1
