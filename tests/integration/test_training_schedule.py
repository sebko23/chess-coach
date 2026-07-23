"""Integration tests for training queue, schedule, and review routes."""
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

class TestTrainingQueue:
    async def test_queue_returns_cards(self, prod_client):
        r = await prod_client.get("/v1/training/queue/ebassti?limit=5", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert "cards" in data
        assert "due_count" in data
        assert len(data["cards"]) <= 5

    async def test_queue_cards_have_required_fields(self, prod_client):
        r = await prod_client.get("/v1/training/queue/ebassti?limit=1", headers=AUTH)
        assert r.status_code == 200
        cards = r.json()["cards"]
        if cards:
            card = cards[0]
            assert "id" in card
            assert "card_type" in card
            assert "stability" in card
            assert "difficulty" in card
            assert "retrievability" in card

    async def test_queue_no_auth_returns_401(self, prod_client):
        r = await prod_client.get("/v1/training/queue/ebassti")
        assert r.status_code == 401

    async def test_queue_limit_respected(self, prod_client):
        r = await prod_client.get("/v1/training/queue/ebassti?limit=3", headers=AUTH)
        assert r.status_code == 200
        assert len(r.json()["cards"]) <= 3

class TestTrainingSchedule:
    async def test_schedule_returns_7_days(self, prod_client):
        r = await prod_client.get(
            "/v1/training/schedule/ebassti?days=7&daily_minutes=30", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert "schedule" in data
        assert len(data["schedule"]) == 7

    async def test_schedule_day_has_required_fields(self, prod_client):
        r = await prod_client.get(
            "/v1/training/schedule/ebassti?days=3&daily_minutes=20", headers=AUTH)
        assert r.status_code == 200
        day = r.json()["schedule"][0]
        assert "day" in day
        assert "date" in day
        assert "estimated_minutes" in day
        assert "cards" in day

    async def test_schedule_no_auth_returns_401(self, prod_client):
        r = await prod_client.get("/v1/training/schedule/ebassti")
        assert r.status_code == 401

class TestTrainingReview:
    async def test_review_valid_rating_returns_200(self, prod_client):
        r = await prod_client.get("/v1/training/queue/ebassti?limit=1", headers=AUTH)
        cards = r.json().get("cards", [])
        if not cards:
            pytest.skip("No cards available for review test")
        card_id = cards[0]["id"]
        r = await prod_client.post(
            f"/v1/training/review/{card_id}",
            headers=AUTH,
            json={"rating": 3},
        )
        assert r.status_code == 200
        data = r.json()
        assert "new_difficulty" in data
        assert "new_due" in data
        assert "new_retrievability" in data

    async def test_review_invalid_rating_returns_422(self, prod_client):
        r = await prod_client.post(
            "/v1/training/review/nonexistent-id",
            headers=AUTH,
            json={"rating": 99},
        )
        assert r.status_code in (422, 404)

    async def test_review_no_auth_returns_401(self, prod_client):
        r = await prod_client.post("/v1/training/review/some-id", json={"rating": 3})
        assert r.status_code == 401
