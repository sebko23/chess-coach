"""Shared pytest fixtures for integration tests under tests/integration/.

Mirrors the pattern in tests/perf/conftest.py: certain integration
tests deliberately need real external services (a live Qdrant, the
gateway with full lifespan, etc.) and must bypass the top-level
tests/conftest.py autouse `_isolate_env` fixture, which would
otherwise strip CHESS_COACH_* env vars and force a private tmp_path
data dir.

The default `_isolate_env` fixture is fine for unit tests that want
to mock the gateway in-process. The tests in tests/integration/
that need real services opt out by using the fixtures defined here.

Marker convention: tests in this directory should carry either
`@pytest.mark.integration` or `@pytest.mark.smoke` (defined in
pyproject.toml). The --strict-markers addopts means a test with no
marker will be rejected.
"""
from __future__ import annotations

import os
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

_QDRANT_URL = os.environ.get("CHESS_COACH_QDRANT_URL")
_QDRANT_API_KEY = os.environ.get("CHESS_COACH_QDRANT_API_KEY")

# Tests in tests/integration/ that need a live Qdrant set the env
# var CHESS_COACH_QDRANT_URL before invoking pytest. The autouse
# _isolate_env fixture in tests/conftest.py would strip it; this
# fixture re-installs the pre-test value into the monkeypatch'd env.
#
# Without this, the GatewaySettings() call inside
# tests/integration/test_kb_qdrant_live.py reads from the
# (now-stripped) env and returns qdrant_url=":memory:".

@pytest.fixture(autouse=True)
def _restore_qdrant_env(monkeypatch) -> None:
    """Re-install CHESS_COACH_QDRANT_URL after tests/conftest.py strips it.

    The pytest CLI is invoked with `CHESS_COACH_QDRANT_URL=...` set in
    the qdrant-smoke job (see .github/workflows/smoke.yml). The top-level
    autouse fixture wipes it before the test body runs; we put it back
    so the test can actually use the sidecar.
    """
    # The env var is captured from the pytest process before the
    # top-level _isolate_env fixture deletes it; this fixture then
    # restores the captured value before GatewaySettings is built.
    if _QDRANT_URL:
        monkeypatch.setenv("CHESS_COACH_QDRANT_URL", _QDRANT_URL)
    if _QDRANT_API_KEY is not None:
        monkeypatch.setenv("CHESS_COACH_QDRANT_API_KEY", _QDRANT_API_KEY)
    return


@pytest.fixture
def qdrant_sqlite_path(tmp_path: Path) -> Path:
    """Create a deterministic SQLite fixture with five indexable positions."""
    db_path = tmp_path / "data" / "sqlite" / "chess_coach.db"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE positions (
                fen TEXT NOT NULL,
                ply INTEGER NOT NULL,
                game_id TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT INTO positions(fen, ply, game_id) VALUES (?, ?, ?)",
            [
                (
                    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
                    4,
                    "qdrant-game-1",
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq d3 0 1",
                    5,
                    "qdrant-game-2",
                ),
                (
                    "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 2",
                    6,
                    "qdrant-game-3",
                ),
                (
                    "r1bq1rk1/pp2bppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R1BQR1K1 w - - 4 10",
                    20,
                    "qdrant-game-4",
                ),
                (
                    "2r2rk1/pp1b1ppp/2n1pn2/q2p4/3P4/2PBPN2/PPQ2PPP/R1B2RK1 w - - 8 12",
                    24,
                    "qdrant-game-5",
                ),
            ],
        )
    return db_path


@pytest.fixture
def settings(qdrant_sqlite_path: Path):
    """GatewaySettings wired to the live Qdrant URL and deterministic SQLite fixture."""
    from chess_coach.gateway.config import GatewaySettings

    return GatewaySettings(data_dir=qdrant_sqlite_path.parents[1])


@pytest.fixture
def app(settings):
    """FastAPI app with the live env-driven settings."""
    from chess_coach.gateway import create_app

    return create_app(settings)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c
