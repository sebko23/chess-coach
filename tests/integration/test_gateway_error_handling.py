"""Integration tests for route_guard and error handling (ADR-0002)."""
from __future__ import annotations
import pytest
import pytest_asyncio
import httpx

AUTH = {"Authorization": "Bearer devtoken123"}


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

class TestErrorEnvelope:
    async def test_404_has_error_envelope(self, prod_client):
        r = await prod_client.get("/v1/games/nonexistent-uuid-1234/pgn", headers=AUTH)
        assert r.status_code == 404
        data = r.json()
        assert "code" in data.get("error", data)

    async def test_401_has_error_envelope(self, prod_client):
        r = await prod_client.get("/v1/games")
        assert r.status_code == 401
        data = r.json()
        assert "code" in data.get("error", data)

    async def test_invalid_token_returns_401(self, prod_client):
        r = await prod_client.get("/v1/games", headers={"Authorization": "Bearer wrongtoken"})
        assert r.status_code == 401

    async def test_missing_required_query_param_returns_422(self, prod_client):
        r = await prod_client.get("/v1/blunders/by-fen", headers=AUTH)
        assert r.status_code == 422
        data = r.json()
        assert "code" in data.get("error", data)

class TestRouteGuard:
    async def test_route_guard_never_returns_500_on_unknown_player(self, prod_client):
        r = await prod_client.get("/v1/profile/player_that_does_not_exist_xyz123", headers=AUTH)
        assert r.status_code != 500

    async def test_route_guard_preserves_200_on_success(self, prod_client):
        r = await prod_client.get("/v1/profile/ebassti", headers=AUTH)
        assert r.status_code == 200
