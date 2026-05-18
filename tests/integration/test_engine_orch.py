"""Integration tests for the engine pool with real Stockfish."""
from __future__ import annotations

import pathlib
import subprocess

import pytest

from chess_coach.engine_orch.pool import EnginePool, EngineSpec
from chess_coach.protocol_types.analysis import AnalysisRequest, AnalysisResult


def _find_stockfish() -> str | None:
    for p in ["/usr/local/bin/stockfish", "stockfish"]:
        try:
            r = subprocess.run(
                [p],
                input="uci\nquit\n",
                text=True,
                capture_output=True,
                timeout=10,
            )
            if "uciok" in r.stdout:
                return p
        except Exception:
            continue
    return None


@pytest.mark.integration
class TestRealStockfish:
    """Tests that require a real Stockfish binary."""

    @pytest.fixture
    async def pool(self):
        path = _find_stockfish()
        if path is None:
            pytest.skip("Stockfish not found")
        pool = EnginePool([EngineSpec(engine_id="sf", path=path)])
        yield pool
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_starting_position_analysis(self, pool):
        req = AnalysisRequest(
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            depth=8,
        )
        result = await pool.analyze(req, "sf")
        assert isinstance(result, AnalysisResult)
        assert result.engine_id == "sf"
        assert len(result.pvs) >= 1
        top_move = result.pvs[0].moves[0]
        assert top_move in ("e2e4", "d2d4", "c2c4", "g1f3"), f"unexpected top move: {top_move}"

    @pytest.mark.asyncio
    async def test_depth_reached_matches_request(self, pool):
        req = AnalysisRequest(
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            depth=6,
        )
        result = await pool.analyze(req, "sf")
        assert result.depth_reached >= 6

    @pytest.mark.asyncio
    async def test_multipv_returns_multiple_pvs(self, pool):
        req = AnalysisRequest(
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            depth=8,
            multipv=3,
        )
        result = await pool.analyze(req, "sf")
        assert len(result.pvs) == 3
        assert result.pvs[0].multipv == 1
        assert result.pvs[1].multipv == 2
        assert result.pvs[2].multipv == 3

    @pytest.mark.asyncio
    async def test_analysis_result_has_cache_fields(self, pool):
        req = AnalysisRequest(
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            depth=6,
        )
        result = await pool.analyze(req, "sf")
        assert result.settings_hash
        assert result.cpu_arch
        assert result.thread_count >= 1
        assert result.engine_version
