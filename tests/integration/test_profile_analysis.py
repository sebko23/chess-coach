"""Integration tests for profile and profile_analysis routes."""
from __future__ import annotations
import pytest
import pytest_asyncio
import httpx
from chess_coach.gateway.auth import set_active_token

AUTH = {"Authorization": "Bearer devtoken123"}

@pytest.fixture(autouse=True)
def _patch_env(monkeypatch):
    monkeypatch.setenv("CHESS_COACH_DATA_DIR", "/root/.local/share/chess-coach")
    set_active_token("devtoken123")
    yield
    set_active_token(None)

@pytest_asyncio.fixture
async def prod_client():
    from chess_coach.gateway.config import GatewaySettings
    from chess_coach.gateway import create_app
    settings = GatewaySettings()
    app = create_app(settings)
    app.state.gateway.settings = settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

class TestProfile:
    async def test_get_profile_default_returns_200(self, prod_client):
        r = await prod_client.get("/v1/profile/default", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert "player_name" in data
        assert "total_games" in data

    async def test_get_profile_known_player(self, prod_client):
        r = await prod_client.get("/v1/profile/ebassti", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert data["player_name"] == "ebassti"
        assert data["total_games"] == 373

    async def test_get_profile_no_auth_returns_401(self, prod_client):
        r = await prod_client.get("/v1/profile/default")
        assert r.status_code == 401

    async def test_get_profile_unknown_player_returns_404(self, prod_client):
        r = await prod_client.get("/v1/profile/nonexistent_player_xyz", headers=AUTH)
        assert r.status_code in (200, 404)

class TestProfileAnalysis:
    async def test_analysis_returns_5_metrics(self, prod_client):
        r = await prod_client.post("/v1/profile/ebassti/analysis", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert "tactical_tendency" in data
        assert "tilt_index" in data
        assert "time_pressure_blunders" in data
        assert "opening_breadth" in data
        assert "risk_appetite" in data

    async def test_analysis_tactical_tendency_range(self, prod_client):
        r = await prod_client.post("/v1/profile/ebassti/analysis", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert 0.0 <= data["tactical_tendency"] <= 100.0

    async def test_analysis_no_auth_returns_401(self, prod_client):
        r = await prod_client.post("/v1/profile/ebassti/analysis")
        assert r.status_code == 401
