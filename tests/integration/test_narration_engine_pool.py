"""BBF-87.2 integration test: the narration route invokes engine_pool.analyze().

End-to-end test of POST /v1/narration/explain with engine fields present:
  - When the request supplies `depth` / `engine_id` / `multipv`, the
    route calls `engine_pool.analyze()` exactly once with the
    AnalysisRequest built from those fields.
  - When the request supplies NO engine fields, the route does NOT
    call `engine_pool.analyze()` and falls through to
    `pipeline.explain_simple()` (backwards-compat path).

Mirrors the `engine_client` fixture pattern from
`tests/integration/test_api_routes.py:42-83`. Uses a stub LLM router
returning a pre-canned narration so the test doesn't depend on
OpenRouter; uses a stub `EnginePool.analyze()` returning a real-shaped
`AnalysisResult` (built via `MagicMock` so we don't need a live
Stockfish process).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest_asyncio

from chess_coach.narration.pipeline import NarrationOutput, NarrationPipeline

# FEN used throughout this test module.
_STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _make_analysis_result_mock() -> MagicMock:
    """Build a MagicMock that mimics AnalysisResult closely enough
    for the route's downstream reads.

    The route reads (after pipeline.explain()):
      - analysis.depth_reached (int)
      - analysis.pvs[0].moves[0] (str — best_move)
    Pipeline.explain() consumes analysis itself (fen, pvs, depth,
    cpu_arch, etc.) — see services/chess_coach/narration/pipeline.py.
    """
    result = MagicMock()
    result.fen = _STARTING_FEN
    result.depth_reached = 12
    result.engine_id = "stockfish"
    result.engine_version = "16"
    result.settings_hash = "abc123"
    result.cpu_arch = "x86_64"
    result.thread_count = 1
    result.multipv = 1
    # Top PV: real moves in UCI (the engine pool emits UCI).
    pv = MagicMock()
    pv.moves = ["e2e4", "e7e5", "g1f3"]
    score = MagicMock()
    score.kind = "cp"
    score.value = 38  # +0.38
    pv.score = score
    pv.depth = 12
    result.pvs = [pv]
    return result


@pytest_asyncio.fixture
async def engine_pool_client() -> httpx.AsyncClient:
    """Client with a mocked engine_pool + a stubbed narration_pipeline.

    The narration_pipeline is the SPEC mock so we can assert on which
    method the route calls (explain vs explain_simple).
    """
    from chess_coach.gateway import create_app
    from chess_coach.gateway.config import GatewaySettings

    settings = GatewaySettings()
    settings.qdrant_url = ":memory:"
    app = create_app(settings)
    app.state.gateway.settings = settings

    # Mock the engine pool: analyze() returns a real-shape AnalysisResult.
    mock_result = _make_analysis_result_mock()
    mock_pool = MagicMock()
    mock_pool.analyze = AsyncMock(return_value=mock_result)
    app.state.engine_pool = mock_pool

    # Mock the narration pipeline so we can assert which method runs.
    mock_pipeline = MagicMock(spec=NarrationPipeline)
    # explain() returns (narration_text, corpus_entry_id) — match the
    # pipeline's actual signature at services/chess_coach/narration/pipeline.py:139.
    mock_pipeline.explain = AsyncMock(
        return_value=(
            "Try <move>e4</move> with eval <eval>+0.38</eval>.",
            None,  # corpus_entry_id
        )
    )
    mock_pipeline.explain_simple = AsyncMock(
        return_value=NarrationOutput(
            narration="Synthetic path narration. No engine call.",
            pv_moves=[],
            score_display="",
        )
    )
    app.state.narration_pipeline = mock_pipeline

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac


AUTH = {"Authorization": "Bearer devtoken123"}


class TestNarrationEnginePoolWired:
    """BBF-87.2: the route invokes engine_pool.analyze() when engine
    fields are present in the request body, and falls through to
    explain_simple() when they are not.
    """

    async def test_engine_fields_present_calls_analyze_once(
        self, engine_pool_client: httpx.AsyncClient,
    ) -> None:
        """POST /v1/narration/explain with depth=12 calls
        engine_pool.analyze() exactly once."""
        r = await engine_pool_client.post(
            "/v1/narration/explain",
            json={
                "fen": _STARTING_FEN,
                "move_san": "e4",
                "eval_cp": 38,
                "depth": 12,
                "engine_id": "stockfish",
                "multipv": 1,
            },
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        engine_pool = engine_pool_client._transport.app.state.engine_pool
        engine_pool.analyze.assert_awaited_once()

    async def test_engine_fields_present_calls_pipeline_explain(
        self, engine_pool_client: httpx.AsyncClient,
    ) -> None:
        """When engine fields are present, the route uses pipeline.explain()
        (not explain_simple())."""
        r = await engine_pool_client.post(
            "/v1/narration/explain",
            json={
                "fen": _STARTING_FEN,
                "depth": 12,
            },
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        pipeline = engine_pool_client._transport.app.state.narration_pipeline
        pipeline.explain.assert_awaited_once()
        pipeline.explain_simple.assert_not_awaited()

    async def test_response_carries_real_pv_from_engine(
        self, engine_pool_client: httpx.AsyncClient,
    ) -> None:
        """When engine-backed, response.pv_moves / score_display are
        populated from the AnalysisResult (real engine moves), not the
        empty synthetic fallback."""
        r = await engine_pool_client.post(
            "/v1/narration/explain",
            json={"fen": _STARTING_FEN, "depth": 12},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # The mock PV is ["e2e4", "e7e5", "g1f3"], truncated to 6 by
        # _format_pv_fields (see services/chess_coach/narration/pipeline.py:71).
        assert body["pv_moves"] == ["e2e4", "e7e5", "g1f3"]
        assert body["score_display"] == "+0.38"

    async def test_response_carries_depth_reached_and_best_move(
        self, engine_pool_client: httpx.AsyncClient,
    ) -> None:
        """When engine-backed, response.depth_reached + best_move
        are populated from the AnalysisResult (was None before)."""
        r = await engine_pool_client.post(
            "/v1/narration/explain",
            json={"fen": _STARTING_FEN, "depth": 12},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["depth_reached"] == 12
        assert body["best_move"] == "e2e4"

    async def test_no_engine_fields_skips_analyze(
        self, engine_pool_client: httpx.AsyncClient,
    ) -> None:
        """When no engine fields are present (current GUI call shape),
        engine_pool.analyze() is NOT called and the route falls through
        to explain_simple() (backwards-compat)."""
        r = await engine_pool_client.post(
            "/v1/narration/explain",
            json={
                "fen": _STARTING_FEN,
                "move_san": "e4",
                "eval_cp": 38,
                "game_phase": "opening",
                "context": "After King's Pawn opening.",
            },
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        engine_pool = engine_pool_client._transport.app.state.engine_pool
        pipeline = engine_pool_client._transport.app.state.narration_pipeline
        engine_pool.analyze.assert_not_awaited()
        pipeline.explain_simple.assert_awaited_once()
        pipeline.explain.assert_not_awaited()
        body = r.json()
        # Synthetic path: depth_reached + best_move stay None.
        assert body["depth_reached"] is None
        assert body["best_move"] is None
        # pv_moves is empty (synthetic path).
        assert body["pv_moves"] == []

    async def test_engine_pool_failure_returns_5xx(
        self, engine_pool_client: httpx.AsyncClient,
    ) -> None:
        """When engine_pool.analyze() raises, the route surfaces a 5xx
        via @route_guard (NOT a 200 with synthetic fallback)."""
        from chess_coach.engine_orch.pool import EngineHungError
        engine_pool = engine_pool_client._transport.app.state.engine_pool
        engine_pool.analyze = AsyncMock(
            side_effect=EngineHungError(
                engine_id="stockfish", slot_index=0, timeout_s=30.0,
            )
        )
        r = await engine_pool_client.post(
            "/v1/narration/explain",
            json={"fen": _STARTING_FEN, "depth": 12},
            headers=AUTH,
        )
        # route_guard converts unhandled exceptions to a 500 envelope.
        # The exact status code depends on the route_guard implementation;
        # the contract is "not 200 with synthetic fallback."
        assert r.status_code != 200, (
            f"engine pool failure should not return 200; got {r.status_code}"
        )
