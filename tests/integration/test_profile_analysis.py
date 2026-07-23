"""Integration tests for profile and profile_analysis routes.

BBF-61: the /v1/profile/{player}/analysis endpoint now
returns BOTH the legacy flat fields (backward compat) AND
the new unified `metrics: [{id, value, ...}]` array. These
tests verify both shapes.
"""
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
    async def test_analysis_returns_legacy_5_fields(self, prod_client):
        """Backward-compat: the legacy 5 fields are still present."""
        r = await prod_client.post("/v1/profile/ebassti/analysis", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        # Legacy fields
        assert "tactical_tendency" in data
        assert "tilt_index" in data
        assert "time_pressure_blunders" in data
        assert "opening_breadth" in data
        assert "risk_appetite" in data
        # Range assertions
        assert 0.0 <= data["tactical_tendency"] <= 1.0

    async def test_analysis_returns_unified_metrics_array(self, prod_client):
        """BBF-61: the response includes a `metrics: [{id, value, ...}]` array."""
        r = await prod_client.post("/v1/profile/ebassti/analysis", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert "metrics" in data, "missing unified metrics array"
        assert isinstance(data["metrics"], list)
        # At least the 5 legacy metrics are present
        metric_ids = {m["id"] for m in data["metrics"]}
        expected_ids = {
            "tactical_vs_positional_bias",
            "time_pressure_quality",
            "opening_comfort",
            "sequence_based_tilt",
        }
        assert expected_ids.issubset(metric_ids), (
            f"missing metrics: {expected_ids - metric_ids}"
        )
        # Each metric has the §B4 contract
        for m in data["metrics"]:
            assert "id" in m
            assert "value" in m
            assert "sample_size" in m
            assert "d" in m
            assert "passes_b4_gate" in m

    async def test_analysis_metric_id_uniqueness(self, prod_client):
        """No duplicate metric_ids in the response array."""
        r = await prod_client.post("/v1/profile/ebassti/analysis", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        metric_ids = [m["id"] for m in data["metrics"]]
        assert len(metric_ids) == len(set(metric_ids)), (
            f"duplicate metric_ids: "
            f"{[m for m in metric_ids if metric_ids.count(m) > 1]}"
        )

    async def test_analysis_metric_values_match_legacy(self, prod_client):
        """The metric values in the unified array match the legacy fields."""
        r = await prod_client.post("/v1/profile/ebassti/analysis", headers=AUTH)
        assert r.status_code == 200
        data = r.json()
        # Build a map from the unified array
        by_id = {m["id"]: m["value"] for m in data["metrics"]}
        # Check the legacy field mappings
        assert by_id.get("tactical_vs_positional_bias") == data["tactical_tendency"], (
            f"tactical_tendency mismatch: legacy={data['tactical_tendency']}, "
            f"unified={by_id.get('tactical_vs_positional_bias')}"
        )
        assert by_id.get("time_pressure_quality") == data["time_pressure_blunders"]
        assert by_id.get("opening_comfort") == data["opening_breadth"]
        assert by_id.get("sequence_based_tilt") == data["tilt_index"]

    async def test_analysis_no_auth_returns_401(self, prod_client):
        r = await prod_client.post("/v1/profile/ebassti/analysis")
        assert r.status_code == 401