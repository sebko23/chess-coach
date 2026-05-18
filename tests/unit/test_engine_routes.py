"""Unit tests for engine + analysis routes (mock pool)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from chess_coach.gateway.app import create_app
from chess_coach.gateway.config import GatewaySettings
from chess_coach.gateway.auth import set_active_token
from chess_coach.engine_orch.pool import EnginePool, EngineSpec
from chess_coach.testkit.mock_uci import MockUCIEngine


@pytest.fixture
def app_with_mock():
    """Create an app with a mock engine pool and auth disabled for tests."""
    set_active_token(None)
    settings = GatewaySettings(data_dir="/tmp/test_engine_" + str(id(object())))
    app = create_app(settings)
    mock = MockUCIEngine()
    app.state.engine_pool = EnginePool([
        EngineSpec(engine_id="stockfish", path="/mock/stockfish"),
        EngineSpec(engine_id="sf", path="/mock/stockfish"),
    ])

    async def mock_acquire(spec, options):
        await mock.start(options=options)
        return mock

    async def mock_release(engine, engine_id):
        pass

    async def _engine_info_async(engine_id):
        if engine_id not in ("stockfish", "sf"):
            raise ValueError(f"Unknown engine: {engine_id}")
        return {
            "engine_id": engine_id,
            "name": "Mock Engine 1.0",
            "version": "1.0",
            "path": "/mock/stockfish",
            "state": "ready",
            "capabilities": [],
        }

    app.state.engine_pool._acquire = mock_acquire
    app.state.engine_pool._release = mock_release
    app.state.engine_pool.engine_info = _engine_info_async
    return app


@pytest.fixture
def client(app_with_mock):
    return TestClient(app_with_mock)


class TestEngineRoutes:
    def test_get_engine_info(self, client):
        resp = client.get("/v1/engines/stockfish")
        assert resp.status_code == 200
        info = resp.json()["data"]
        assert info["engine_id"] == "stockfish"

    def test_get_engine_info_not_found(self, client):
        resp = client.get("/v1/engines/nonexistent")
        assert resp.status_code == 404

    def test_analyze_returns_pvs(self, client):
        body = {
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "depth": 10,
            "multipv": 1,
        }
        resp = client.post("/v1/engines/stockfish/analyze", json=body)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "pvs" in data
        assert len(data["pvs"]) >= 1

    def test_analysis_shortcut_route(self, client):
        body = {
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "depth": 10,
        }
        resp = client.post("/v1/analysis/positions", json=body)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["engine_id"] == "stockfish"

    def test_analyze_unknown_engine(self, client):
        body = {
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        }
        resp = client.post("/v1/engines/nonexistent/analyze", json=body)
        assert resp.status_code == 404
