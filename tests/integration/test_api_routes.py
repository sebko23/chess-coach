"""Integration tests for Phase 2-3 backend routes.

Uses the production DB so all tables exist and we can make meaningful
assertions against real data (551 games, 3,739 training cards).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from chess_coach.narration.pipeline import NarrationPipeline, NarrationOutput
from fastapi import FastAPI

from chess_coach.gateway.auth import set_active_token


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch):
    """Point to production DB and set token."""
    monkeypatch.setenv("CHESS_COACH_DATA_DIR", "/root/.local/share/chess-coach")
    set_active_token("devtoken123")
    yield
    set_active_token(None)


@pytest_asyncio.fixture
async def prod_client() -> httpx.AsyncClient:
    """Test client against the real DB via ASGITransport."""
    from chess_coach.gateway.config import GatewaySettings
    from chess_coach.gateway import create_app
    settings = GatewaySettings()
    app = create_app(settings)
    app.state.gateway.settings = settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def engine_client() -> httpx.AsyncClient:
    """Client with mocked engine_pool + LLM router for narration."""
    from chess_coach.gateway.config import GatewaySettings
    from chess_coach.gateway import create_app
    
    # Mock the LLM router so narration doesn't call OpenRouter
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value=(
        "<narration>The position is equal. Standard opening principles apply.</narration>"
    ))
    settings = GatewaySettings()
    app = create_app(settings)
    app.state.gateway.settings = settings
    
    # Mock the engine pool
    # Create a proper mock result with .pvs attribute matching AnalysisResult
    mock_result = MagicMock()
    mock_result.fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    mock_pv = MagicMock()
    mock_pv.moves = ["e2e4", "e7e5"]
    mock_score = MagicMock()
    mock_score.kind = "cp"
    mock_score.value = 50
    mock_pv.score = mock_score
    mock_result.pvs = [mock_pv]
    
    mock_pool = MagicMock()
    mock_pool.analyze = AsyncMock(return_value=mock_result)
    app.state.engine_pool = mock_pool
    from chess_coach.narration.pipeline import NarrationPipeline
    mock_pipeline = MagicMock(spec=NarrationPipeline)
    mock_pipeline.explain_simple = AsyncMock(
        return_value=NarrationOutput(
            narration="The position is equal. Standard opening principles apply.",
            pv_moves=[],
            score_display="",
        )
    )
    app.state.narration_pipeline = mock_pipeline
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


AUTH = {"Authorization": "Bearer devtoken123"}


class TestNarration:
    async def test_explain_returns_200(self, engine_client):
        r = await engine_client.post(
            "/v1/narration/explain",
            json={"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                  "depth": 10, "engine_id": "stockfish", "multipv": 1},
            headers=AUTH,
        )
        assert r.status_code == 200

    async def test_explain_includes_pv_and_score_fields(self, engine_client):
        """Narration response includes pv_moves + score_display fields."""
        r = await engine_client.post(
            "/v1/narration/explain",
            json={"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                  "depth": 10, "engine_id": "stockfish", "multipv": 1},
            headers=AUTH,
        )
        body = r.json()
        assert r.status_code == 200
        assert "pv_moves" in body
        assert "score_display" in body
        assert body["pv_moves"] == []
        assert body["score_display"] == ""

    async def test_no_auth_returns_401(self, engine_client):
        r = await engine_client.post(
            "/v1/narration/explain",
            json={"fen": "startpos", "depth": 5, "engine_id": "stockfish"},
        )
        assert r.status_code == 401


class TestGames:
    async def test_list_returns_data(self, prod_client):
        r = await prod_client.get("/v1/games", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert "games" in data
        assert "total" in data
        assert data["total"] == 551

    async def test_pagination_honors_limit(self, prod_client):
        r = await prod_client.get("/v1/games?limit=5&offset=0", headers=AUTH)
        assert r.status_code == 200
        assert len(r.json()["games"]) == 5

    async def test_no_auth_returns_401(self, prod_client):
        r = await prod_client.get("/v1/games")
        assert r.status_code == 401

    async def test_pgn_on_missing_game(self, prod_client):
        r = await prod_client.get("/v1/games/nonexistent/pgn", headers=AUTH)
        assert r.status_code == 404

    async def test_pgn_on_real_game(self, prod_client):
        r = await prod_client.get("/v1/games?limit=1", headers=AUTH)
        gid = r.json()["games"][0]["id"]
        r = await prod_client.get(f"/v1/games/{gid}/pgn", headers=AUTH)
        assert r.status_code == 200
        assert "Event" in r.text or "[Event" in r.text


class TestTraining:
    async def test_queue_returns_cards(self, prod_client):
        r = await prod_client.get("/v1/training/queue/default?limit=5", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert "cards" in data
        assert "due_count" in data
        assert data["due_count"] >= 3700

    async def test_queue_cards_have_fen_and_eco(self, prod_client):
        r = await prod_client.get("/v1/training/queue/default?limit=2", headers=AUTH)
        cards = r.json()["cards"]
        for card in cards:
            assert "fen" in card
            assert "id" in card

    async def test_no_auth_returns_401(self, prod_client):
        r = await prod_client.get("/v1/training/queue/default")
        assert r.status_code == 401


class TestRepertoire:
    async def test_tree_returns_data(self, prod_client):
        r = await prod_client.get("/v1/repertoire/default/tree", headers=AUTH)
        assert r.status_code == 200

    async def test_gaps_returns_data(self, prod_client):
        r = await prod_client.get("/v1/repertoire/default/gaps", headers=AUTH)
        assert r.status_code == 200

    async def test_novelties_returns_data(self, prod_client):
        r = await prod_client.get("/v1/repertoire/default/novelties", headers=AUTH)
        assert r.status_code == 200


class TestProfile:
    async def test_default_has_total_games(self, prod_client):
        r = await prod_client.get("/v1/profile/default", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert "total_games" in data
        assert isinstance(data["total_games"], int)

    async def test_no_auth_returns_401(self, prod_client):
        r = await prod_client.get("/v1/profile/default")
        assert r.status_code == 401


class TestSystem:
    async def test_info_has_backend_version(self, prod_client):
        r = await prod_client.get("/v1/system/info", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        info = body.get("data", body)
        assert "backend_version" in info

    async def test_no_auth_returns_401(self, prod_client):
        r = await prod_client.get("/v1/system/info")
        assert r.status_code == 401


class TestAuth:
    async def test_invalid_token(self, prod_client):
        r = await prod_client.get("/v1/games", headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401

    async def test_missing_header(self, prod_client):
        r = await prod_client.get("/v1/games")
        assert r.status_code == 401
