"""Integration tests for PDF import route (chessvision.ai integration)."""
from __future__ import annotations
import io
from unittest.mock import AsyncMock, patch
import pytest
import pytest_asyncio
import httpx
from chess_coach.gateway.auth import set_active_token

AUTH = {"Authorization": "Bearer devtoken123"}
MOCK_FEN = "8/8/8/4k3/8/8/8/4K2R w K - 0 1"

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

def _minimal_pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"

class TestPdfImport:
    async def test_no_auth_returns_401(self, prod_client):
        r = await prod_client.post("/v1/import/pdf", files={"file": ("test.pdf", io.BytesIO(_minimal_pdf()), "application/pdf")})
        assert r.status_code == 401

    async def test_empty_file_returns_400(self, prod_client):
        r = await prod_client.post("/v1/import/pdf", headers=AUTH, files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")})
        assert r.status_code == 400

    async def test_invalid_pdf_returns_422(self, prod_client):
        r = await prod_client.post("/v1/import/pdf", headers=AUTH, files={"file": ("bad.pdf", io.BytesIO(b"not a pdf"), "application/pdf")})
        assert r.status_code == 422

    @patch("services.chess_coach.gateway.routes.pdf_ingest._predict_fen", new_callable=AsyncMock, return_value=(MOCK_FEN, 0.9, None))
    async def test_valid_pdf_returns_import_response(self, mock_predict, prod_client):
        r = await prod_client.post("/v1/import/pdf", headers=AUTH, files={"file": ("test.pdf", io.BytesIO(_minimal_pdf()), "application/pdf")}, params={"max_pages": 1})
        assert r.status_code == 200
        data = r.json()
        assert "import_id" in data
        assert "pages_processed" in data
        assert "diagrams_found" in data
        assert "diagrams" in data
