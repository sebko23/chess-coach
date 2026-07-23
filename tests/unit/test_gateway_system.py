"""End-to-end-ish tests for the /v1/system/* endpoints.

Uses ``httpx.AsyncClient`` with ASGITransport (no real socket). Auth is
seeded explicitly via :func:`set_active_token`.
"""
from __future__ import annotations

import httpx
import pytest

from chess_coach.gateway.auth import set_active_token

VALID = "unit-test-bearer"
AUTH = {"Authorization": f"Bearer {VALID}"}


@pytest.fixture(autouse=True)
def _seed_token() -> None:
    set_active_token(VALID)
    yield
    set_active_token(None)


class TestSystemInfo:
    async def test_returns_envelope(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/v1/system/info", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"data"}
        d = body["data"]
        assert d["backend_version"]
        assert d["protocol_min"] == "1.0.0"
        assert d["protocol_max"] == "1.0.0"
        assert isinstance(d["capabilities"], list)
        assert isinstance(d["runtime"], dict)

    async def test_request_id_header_echoed(self, client: httpx.AsyncClient) -> None:
        r = await client.get(
            "/v1/system/info",
            headers={**AUTH, "X-Request-Id": "my-rid-123"},
        )
        assert r.headers.get("X-Request-Id") == "my-rid-123"

    async def test_request_id_generated_when_absent(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/v1/system/info", headers=AUTH)
        rid = r.headers.get("X-Request-Id")
        assert rid
        assert len(rid) >= 8


class TestSystemHealth:
    async def test_returns_envelope(self, client: httpx.AsyncClient) -> None:
        r = await client.get("/v1/system/health", headers=AUTH)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["status"] in ("ok", "degraded", "unhealthy")
        names = {c["name"] for c in d["components"]}
        assert "gateway" in names
        assert d["uptime_seconds"] >= 0.0


class TestAuthEnforcement:
    async def test_missing_authorization_returns_envelope_401(
        self, client: httpx.AsyncClient
    ) -> None:
        r = await client.get("/v1/system/info")
        assert r.status_code == 401
        body = r.json()
        assert "error" in body
        err = body["error"]
        assert err["code"] == "client.unauthorized"
        assert err["retriable"] is False
        assert err["request_id"]  # echoed/generated

    async def test_wrong_token_returns_envelope_401(
        self, client: httpx.AsyncClient
    ) -> None:
        r = await client.get(
            "/v1/system/info", headers={"Authorization": "Bearer nope"}
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "client.unauthorized"

    async def test_unknown_route_returns_envelope_404(
        self, client: httpx.AsyncClient
    ) -> None:
        r = await client.get("/v1/system/does-not-exist", headers=AUTH)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "client.not_found"
