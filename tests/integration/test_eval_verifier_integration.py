"""Integration tests for BBF-64 eval-delta verifier route.

Uses httpx.ASGITransport + monkeypatched engine verify_corpus (NO real Stockfish).
Each test patches the verify_corpus function to inject deterministic results
and asserts the route handler aggregates them correctly.
"""
from __future__ import annotations

import json
import pathlib
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from chess_coach.gateway.app import create_app

CORPUS_V2 = pathlib.Path("tests/gold/L2/v2/corpus.json")
CORPUS_V1 = pathlib.Path("tests/gold/L2/v1/corpus.json")


@pytest.fixture
def fastapi_app():
    return create_app()


@pytest.fixture
def fake_positions_factory():
    """Return a function that, given the engine top-1, produces
    fake PositionReports matching the corpus size. The verifier
    is responsible for the AGGREGATION; positions are mocked here."""

    def _factory(version: str, engine_top: str, engine_score: int):
        corpus_path = CORPUS_V1 if version == "v1" else CORPUS_V2
        raw = json.loads(corpus_path.read_text())
        positions = raw.get("positions", raw)

        from chess_coach.gateway.routes.eval_verifier import PositionReport
        out = []
        for p in positions:
            delta = engine_score - p["score_cp"]
            status = "match_top1" if engine_top == p["best_move_uci"] else "miss"
            out.append(PositionReport(
                id=p["id"],
                fen=p["fen"],
                gold_move_uci=p["best_move_uci"],
                gold_score_cp=p["score_cp"],
                engine_top_move_uci=engine_top,
                engine_top_score_cp=engine_score,
                delta_cp=delta,
                status=status,
            ))
        return out

    return _factory


@pytest.mark.asyncio
async def test_v2_endpoint_returns_18_positions(fastapi_app, fake_positions_factory):
    """Hit /v1/eval/verify/v2 with a deterministic engine mock;
    expect 18 positions in the response."""
    fakes = fake_positions_factory("v2", engine_top="e2e4", engine_score=30)
    with patch("chess_coach.gateway.routes.eval_verifier.verify_corpus",
               new=AsyncMock(return_value=fakes)):
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/v1/eval/verify/v2?depth=10&top_n=1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["corpus_version"] == "v2"
    assert body["summary"]["total"] == 18
    assert len(body["positions"]) == 18


@pytest.mark.asyncio
async def test_v2_summary_aggregation_when_all_match(fastapi_app, fake_positions_factory):
    """If engine top-1 matches every gold move, top1_hits == total."""
    # Use a single engine top move that matches every gold move:
    # only possible if every gold move happens to be the same UCI -- unlikely.
    # Instead, build fakes where each engine top matches its gold move.
    raw = json.loads(CORPUS_V2.read_text())
    positions = raw.get("positions", raw)

    from chess_coach.gateway.routes.eval_verifier import PositionReport
    fakes = []
    for p in positions:
        fakes.append(PositionReport(
            id=p["id"], fen=p["fen"],
            gold_move_uci=p["best_move_uci"], gold_score_cp=p["score_cp"],
            engine_top_move_uci=p["best_move_uci"], engine_top_score_cp=p["score_cp"],
            delta_cp=0, status="match_top1",
        ))

    with patch("chess_coach.gateway.routes.eval_verifier.verify_corpus",
               new=AsyncMock(return_value=fakes)):
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/v1/eval/verify/v2?depth=10&top_n=1")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["top1_hits"] == 18
    assert body["summary"]["top3_hits"] == 18
    assert body["summary"]["score_within_50cp"] == 18
    assert body["summary"]["mean_delta_cp_abs"] == 0.0


@pytest.mark.asyncio
async def test_v1_endpoint_returns_12_positions(fastapi_app, fake_positions_factory):
    """v1 has 12 positions; endpoint should report total=12."""
    fakes = fake_positions_factory("v1", engine_top="d2d4", engine_score=25)
    with patch("chess_coach.gateway.routes.eval_verifier.verify_corpus",
               new=AsyncMock(return_value=fakes)):
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/v1/eval/verify/v1?depth=10&top_n=1")
    assert r.status_code == 200
    body = r.json()
    assert body["corpus_version"] == "v1"
    assert body["summary"]["total"] == 12


@pytest.mark.asyncio
async def test_unknown_version_returns_422(fastapi_app):
    """FastAPI validates path params against the enum; v3 should 422."""
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/v1/eval/verify/v3")
    assert r.status_code == 422  # FastAPI enum-validation response
