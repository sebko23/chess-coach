"""Tests for BBF-63 Task 3: eval_deltas helper."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from services.chess_coach.gold.eval_delta import eval_deltas

from chess_coach.engine_orch.pool import EnginePool
from chess_coach.protocol_types.analysis import AnalysisResult, PVLine, Score


@pytest.mark.asyncio
async def test_eval_deltas_returns_top_n_moves(monkeypatch):
    """A mocked pool result avoids spawning a real Stockfish process."""
    fixed = AnalysisResult(
        engine_id="stockfish",
        engine_version="fake",
        fen="startpos_fen",
        depth_reached=15,
        multipv=2,
        settings_hash="fake",
        cpu_arch="fake",
        thread_count=1,
        pvs=[
            PVLine(
                moves=["e2e4"],
                score=Score(kind="cp", value=28),
                depth=15,
                multipv=1,
            ),
            PVLine(
                moves=["d2d4"],
                score=Score(kind="cp", value=10),
                depth=15,
                multipv=2,
            ),
        ]
    )
    analyze = AsyncMock(return_value=fixed)
    monkeypatch.setattr(EnginePool, "analyze", analyze)

    deltas = await eval_deltas("startpos_fen", depth=15, top_n=3)

    assert deltas == [
        {"move_uci": "e2e4", "score_cp": 28, "delta_cp": 0},
        {"move_uci": "d2d4", "score_cp": 10, "delta_cp": -18},
    ]
    request = analyze.await_args.args[0]
    assert request.fen == "startpos_fen"
    assert request.depth == 15
    assert request.multipv == 3
    assert analyze.await_args.kwargs == {"engine_id": "stockfish"}


@pytest.mark.asyncio
async def test_eval_deltas_delta_increases():
    """An injected fake pool maps PVs without starting an engine."""
    fake_pool = AsyncMock(spec=EnginePool)
    fake_pool.analyze.return_value = AnalysisResult(
        engine_id="stockfish",
        engine_version="fake",
        fen="startpos_fen",
        depth_reached=15,
        multipv=2,
        settings_hash="fake",
        cpu_arch="fake",
        thread_count=1,
        pvs=[
            PVLine(
                moves=["e2e4"],
                score=Score(kind="cp", value=28),
                depth=15,
                multipv=1,
            ),
            PVLine(
                moves=["d2d4"],
                score=Score(kind="cp", value=35),
                depth=15,
                multipv=2,
            ),
        ]
    )

    deltas = await eval_deltas("startpos_fen", pool=fake_pool)

    assert deltas[0]["delta_cp"] == 0
    assert deltas[1]["delta_cp"] == 7
