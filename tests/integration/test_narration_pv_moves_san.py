"""FU-5 integration test: the narration route returns the additive
`pv_moves_san` field alongside the existing `pv_moves` (UCI).

Mirrors the fixture pattern from `tests/integration/test_narration_engine_pool.py`
to keep style + setup consistent with BBF-87.2's integration tests.

Covers both narration paths:
  - engine-backed (depth field present, real engine_pool.analyze() call)
  - synthetic (no engine fields, explain_simple() fallback)

Verifies:
  - pv_moves stays UCI (authoritative, unchanged from prior BBFs)
  - pv_moves_san is the SAN translation, length-aligned 1:1 with pv_moves
  - pv_moves_san uses the replay-on-board implementation (no broken
    "exe5" / "Nxc6" — this is the regression vector the directive was
    designed to prevent)
  - pv_moves_san defaults to [] on the synthetic path
  - The response schema's pv_moves_san field appears in OpenAPI export
    (verified separately in the codegen step)

Spec authority: `specs/v1.0/chess-coach-protocol-v1.md:42` (UCI
authoritative on the wire; SAN is an additional field, never
authoritative).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest_asyncio

from chess_coach.narration.pipeline import NarrationOutput, NarrationPipeline

_STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# An Italian-game 4-ply PV that exercises multi-move replay (the
# canonical case that proves naive per-move conversion is wrong).
# In UCI: e2e4 e7e5 g1f3 b8c6 — the b8c6 move is the disambiguation
# smoking gun; naive `Board(fen).san(b8c6)` emits 'Nxc6' but the
# correct SAN is 'Nc6' because there's no capture on c6 yet.
_ITALIAN_PV_UCI = ["e2e4", "e7e5", "g1f3", "b8c6"]
_ITALIAN_PV_SAN = ["e4", "e5", "Nf3", "Nc6"]


def _make_analysis_result_mock() -> MagicMock:
    """Build a MagicMock that mimics AnalysisResult for the route's
    downstream reads. The route reads (after pipeline.explain()):
      - analysis.depth_reached (int)
      - analysis.pvs[0].moves[0] (str — best_move)
      - analysis.pvs[0].moves (list[str] — full PV)
      - analysis.pvs[0].score.kind / .value (for score_display)
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
    pv = MagicMock()
    pv.moves = list(_ITALIAN_PV_UCI)
    score = MagicMock()
    score.kind = "cp"
    score.value = 38  # +0.38
    pv.score = score
    pv.depth = 12
    result.pvs = [pv]
    return result


@pytest_asyncio.fixture
async def fu5_engine_client() -> httpx.AsyncClient:
    """Client with a mocked engine_pool + a stubbed narration_pipeline.

    Same setup as `tests/integration/test_narration_engine_pool.py`'s
    `engine_pool_client` fixture; the engine-backed path returns a PV
    whose UCI translates to a non-trivial SAN sequence (4-ply Italian
    line, exercises the replay-on-board path).
    """
    from chess_coach.gateway import create_app
    from chess_coach.gateway.config import GatewaySettings

    settings = GatewaySettings()
    settings.qdrant_url = ":memory:"
    app = create_app(settings)
    app.state.gateway.settings = settings

    mock_result = _make_analysis_result_mock()
    mock_pool = MagicMock()
    mock_pool.analyze = AsyncMock(return_value=mock_result)
    app.state.engine_pool = mock_pool

    mock_pipeline = MagicMock(spec=NarrationPipeline)
    mock_pipeline.explain = AsyncMock(
        return_value=(
            "Try <move>e4</move> with eval <eval>+0.38</eval>.",
            None,  # corpus_entry_id
        )
    )
    # Synthetic path returns empty PVs and empty score.
    mock_pipeline.explain_simple = AsyncMock(
        return_value=NarrationOutput(
            narration="Synthetic path narration.",
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


class TestNarrationPvMovesSan:
    """FU-5: the additive `pv_moves_san` field appears on the response
    alongside `pv_moves` (UCI) for both narration paths."""

    async def test_engine_backed_response_has_pv_moves_uci_and_san(
        self, fu5_engine_client: httpx.AsyncClient,
    ) -> None:
        """Engine-backed path: pv_moves stays UCI (authoritative),
        pv_moves_san is the SAN translation, length-aligned."""
        r = await fu5_engine_client.post(
            "/v1/narration/explain",
            json={"fen": _STARTING_FEN, "depth": 12},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        body = r.json()

        # pv_moves unchanged from BBF-87.2 — UCI authoritative.
        assert body["pv_moves"] == _ITALIAN_PV_UCI

        # pv_moves_san is the new additive field with the SAN translation.
        assert "pv_moves_san" in body
        assert body["pv_moves_san"] == _ITALIAN_PV_SAN

        # Lengths aligned 1:1.
        assert len(body["pv_moves"]) == len(body["pv_moves_san"])

    async def test_engine_backed_san_does_not_contain_uci(
        self, fu5_engine_client: httpx.AsyncClient,
    ) -> None:
        """pv_moves_san is genuinely SAN — no UCI strings leaked through."""
        r = await fu5_engine_client.post(
            "/v1/narration/explain",
            json={"fen": _STARTING_FEN, "depth": 12},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Every pv_moves_san element should be non-UCI: no 4-character
        # 'square-from-square-to' shape (e.g. 'e2e4' would be 4 chars
        # but our SAN has 2-3 chars + at most one '=' for promotion).
        for san in body["pv_moves_san"]:
            # UCI strings are exactly 4 chars (or 5 with promotion
            # suffix). SAN strings are 2-6 chars but never look like
            # a4b5c6... e.g. 'e2e4'.
            assert not (
                len(san) in (4, 5)
                and san[0].isalpha()
                and san[1].isdigit()
                and san[2].isalpha()
                and san[3].isdigit()
            ), f"UCI leaked into pv_moves_san: {san!r}"

    async def test_synthetic_path_response_has_empty_pv_moves_san(
        self, fu5_engine_client: httpx.AsyncClient,
    ) -> None:
        """Synthetic path: pv_moves and pv_moves_san both empty."""
        r = await fu5_engine_client.post(
            "/v1/narration/explain",
            json={
                "fen": _STARTING_FEN,
                "move_san": "e4",
                "eval_cp": 38,
                "game_phase": "opening",
            },
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Synthetic: no engine call, both PV lists empty.
        assert body["pv_moves"] == []
        assert body["pv_moves_san"] == []
        assert len(body["pv_moves"]) == len(body["pv_moves_san"])

    async def test_response_schema_declares_pv_moves_san(
        self, fu5_engine_client: httpx.AsyncClient,
    ) -> None:
        """The OpenAPI schema (regenerated by FU-4 codegen) must
        include pv_moves_san as a declared field, not just appearing
        in the JSON body. This is the codegen-pipeline integration
        verification — if the backend schema is missing the field,
        the regenerated TypeScript types won't have it either.
        """
        # Fetch the OpenAPI schema from the live test client. The
        # gateway's create_app() registers the schema at app.openapi().
        app = fu5_engine_client._transport.app
        schema = app.openapi()
        # Locate the NarrationResponse schema component.
        schemas = schema.get("components", {}).get("schemas", {})
        # Pydantic names the schema "<ModelName>" verbatim.
        narration_resp = schemas.get("NarrationRouteResponse") or schemas.get(
            "NarrationResponse"
        )
        assert narration_resp is not None, (
            f"narration schema missing from OpenAPI: {list(schemas.keys())}"
        )
        props = narration_resp.get("properties", {})
        assert "pv_moves_san" in props, (
            f"pv_moves_san missing from schema properties: {list(props.keys())}"
        )
        # And the existing pv_moves is still there (regression check).
        assert "pv_moves" in props
