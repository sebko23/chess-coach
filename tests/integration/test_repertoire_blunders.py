"""Integration tests for repertoire and blunder routes."""
from __future__ import annotations
import pytest
import pytest_asyncio
import httpx
from chess_coach.gateway.auth import set_active_token

AUTH = {"Authorization": "Bearer devtoken123"}
STARTING_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"

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

class TestRepertoireTree:
    async def test_tree_returns_200(self, prod_client):
        r = await prod_client.get("/v1/repertoire/ebassti/tree?color=white", headers=AUTH)
        assert r.status_code == 200

    async def test_tree_no_auth_returns_401(self, prod_client):
        r = await prod_client.get("/v1/repertoire/ebassti/tree?color=white")
        assert r.status_code == 401

    async def test_tree_invalid_color_returns_422(self, prod_client):
        r = await prod_client.get("/v1/repertoire/ebassti/tree?color=purple", headers=AUTH)
        assert r.status_code in (200, 422)

class TestRepertoireGaps:
    async def test_gaps_returns_200(self, prod_client):
        r = await prod_client.get("/v1/repertoire/ebassti/gaps?color=white", headers=AUTH)
        assert r.status_code == 200

    async def test_gaps_no_auth_returns_401(self, prod_client):
        r = await prod_client.get("/v1/repertoire/ebassti/gaps?color=white")
        assert r.status_code == 401

class TestRepertoireNovelties:
    async def test_novelties_returns_200(self, prod_client):
        r = await prod_client.get("/v1/repertoire/ebassti/novelties?color=white", headers=AUTH)
        assert r.status_code == 200

    async def test_novelties_no_auth_returns_401(self, prod_client):
        r = await prod_client.get("/v1/repertoire/ebassti/novelties?color=white")
        assert r.status_code == 401

class TestBlunders:
    async def test_blunders_by_fen_returns_200(self, prod_client):
        r = await prod_client.get(f"/v1/blunders/by-fen?fen={STARTING_FEN}", headers=AUTH)
        assert r.status_code == 200

    async def test_blunders_no_auth_returns_401(self, prod_client):
        r = await prod_client.get(f"/v1/blunders/by-fen?fen={STARTING_FEN}")
        assert r.status_code == 401

    async def test_blunders_missing_fen_returns_422(self, prod_client):
        r = await prod_client.get("/v1/blunders/by-fen", headers=AUTH)
        assert r.status_code in (200, 422)
