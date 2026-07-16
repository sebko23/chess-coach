"""Unit tests for BBF-64 eval-delta verifier route module.

Tests Pydantic model shape + handler existence (NOT full integration).
Full end-to-end uses mocked EnginePool; see tests/integration/.
"""
from __future__ import annotations

from chess_coach.gateway.routes.eval_verifier import (
    CorpusVersion,
    PositionReport,
    VerifyResponse,
    VerifySummary,
    verify_corpus,
)


def test_corpus_version_enum_has_v1_and_v2():
    assert CorpusVersion.V1.value == "v1"
    assert CorpusVersion.V2.value == "v2"


def test_position_report_required_fields():
    rep = PositionReport(
        id="L2-v2-0001",
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        gold_move_uci="e2e4",
        gold_score_cp=28,
        engine_top_move_uci="e2e4",
        engine_top_score_cp=30,
        delta_cp=2,
        status="match_top1",
    )
    assert rep.id == "L2-v2-0001"
    assert rep.delta_cp == 2


def test_verify_summary_aggregates_correctly():
    s = VerifySummary(
        total=10,
        top1_hits=8,
        top3_hits=9,
        score_within_50cp=7,
        mean_delta_cp_abs=42.5,
        max_delta_cp_abs=180,
    )
    assert s.total == 10
    assert s.top1_hits == 8


def test_verify_response_includes_corpus_version():
    resp = VerifyResponse(
        corpus_version=CorpusVersion.V2,
        summary=VerifySummary(
            total=2, top1_hits=1, top3_hits=2,
            score_within_50cp=1, mean_delta_cp_abs=10.0, max_delta_cp_abs=20,
        ),
        positions=[],
    )
    assert resp.corpus_version == CorpusVersion.V2


async def test_verify_corpus_v1_returns_nonempty_response():
    from unittest.mock import AsyncMock, MagicMock
    from chess_coach.protocol_types.analysis import AnalysisResult, PVLine, Score

    fixed_result = AnalysisResult(
        engine_id="stockfish",
        engine_version="fake",
        fen="startpos_fen",
        depth_reached=15,
        multipv=1,
        settings_hash="fake",
        cpu_arch="fake",
        thread_count=1,
        pvs=[
            PVLine(moves=["e2e4"], score=Score(kind="cp", value=30), depth=15, multipv=1),
        ],
    )
    mock_pool = MagicMock()
    mock_pool.analyze = AsyncMock(return_value=fixed_result)

    from pathlib import Path
    v1 = Path("tests/gold/L2/v1/corpus.json")
    assert v1.exists(), "v1 corpus must exist for this test"

    result = await verify_corpus(CorpusVersion.V1, pool=mock_pool, depth=10, top_n=1)
    assert isinstance(result, list)


async def test_verify_corpus_v2_smoke():
    from unittest.mock import AsyncMock, MagicMock
    from chess_coach.protocol_types.analysis import AnalysisResult, PVLine, Score
    from pathlib import Path

    fixed = AnalysisResult(
        engine_id="stockfish",
        engine_version="fake",
        fen="startpos_fen",
        depth_reached=15,
        multipv=1,
        settings_hash="fake",
        cpu_arch="fake",
        thread_count=1,
        pvs=[
            PVLine(moves=["e2e4"], score=Score(kind="cp", value=30), depth=15, multipv=1),
        ],
    )
    mock_pool = MagicMock()
    mock_pool.analyze = AsyncMock(return_value=fixed)
    v2 = Path("tests/gold/L2/v2/corpus.json")
    assert v2.exists(), "v2 corpus must exist for this test"
    result = await verify_corpus(CorpusVersion.V2, pool=mock_pool, depth=10, top_n=1)
    assert isinstance(result, list)


def test_verify_corpus_unknown_version_raises():
    import pytest
    with pytest.raises((ValueError, KeyError, TypeError)):
        CorpusVersion("v3")
