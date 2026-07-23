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
    # Constructor signature: id, fen, gold_move_uci, gold_score_cp,
    # engine_top_move_uci, engine_top_score_cp, delta_cp, status
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
    # Constructor signature: total, top1_hits, top3_hits, score_within_50cp,
    # mean_delta_cp_abs, max_delta_cp_abs
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
    # VerifyResponse = corpus_version, summary, positions
    summary = VerifySummary(
        total=2, top1_hits=1, top3_hits=2,
        score_within_50cp=1, mean_delta_cp_abs=10.0, max_delta_cp_abs=20,
    )
    resp = VerifyResponse(
        corpus_version=CorpusVersion.V2,
        summary=summary,
        positions=[],
    )
    assert resp.corpus_version == CorpusVersion.V2


async def test_verify_corpus_v1_returns_full_reports():
    """v1 has 12 entries; with mocked engine returning e2e4=30cp, every
    position's gold move may or may not match e2e4 -- we just verify
    the function completes and the response shape is correct."""
    from unittest.mock import AsyncMock, MagicMock

    from chess_coach.protocol_types.analysis import AnalysisResult, PVLine, Score

    # Mock engine that returns e2e4=30cp at top-1, d2d4=20cp at PV-2.
    fixed = AnalysisResult(
        engine_id="stockfish",
        engine_version="fake",
        fen="startpos_fen",
        depth_reached=15,
        multipv=3,
        settings_hash="fake",
        cpu_arch="fake",
        thread_count=1,
        pvs=[
            PVLine(moves=["e2e4"], score=Score(kind="cp", value=30), depth=15, multipv=1),
            PVLine(moves=["d2d4"], score=Score(kind="cp", value=20), depth=15, multipv=2),
            PVLine(moves=["c2c4"], score=Score(kind="cp", value=10), depth=15, multipv=3),
        ],
    )
    mock_pool = MagicMock()
    mock_pool.analyze = AsyncMock(return_value=fixed)

    results = await verify_corpus(CorpusVersion.V1, pool=mock_pool, depth=10, top_n=3)
    # v1 has 12 positions
    assert len(results) == 12, f"expected 12 v1 positions in report, got {len(results)}"
    # Each result is a PositionReport
    for r in results:
        assert isinstance(r, PositionReport)
        assert r.engine_top_move_uci == "e2e4"  # mock returned this
        assert r.engine_top_score_cp == 30
        # delta_cp = engine_top - gold
        assert r.delta_cp == 30 - r.gold_score_cp
    # All mock e2e4 - v1 has different gold moves, so status will be mix of miss/topN
    statuses = {r.status for r in results}
    assert statuses.issubset({"match_top1", "match_topN", "miss"})


async def test_verify_corpus_v2_returns_18_reports():
    """v2 has 18 entries; with mocked engine, returns 18 PositionReports."""
    from unittest.mock import AsyncMock, MagicMock

    from chess_coach.protocol_types.analysis import AnalysisResult, PVLine, Score

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

    results = await verify_corpus(CorpusVersion.V2, pool=mock_pool, depth=10, top_n=1)
    assert len(results) == 18
    for r in results:
        assert isinstance(r, PositionReport)


async def test_verify_corpus_top1_match_status():
    """When the engine's top-1 move matches the gold move exactly, status='match_top1'."""
    from unittest.mock import AsyncMock, MagicMock

    from chess_coach.datasets.l2_gold import load_l2_gold
    from chess_coach.protocol_types.analysis import AnalysisResult, PVLine, Score

    # Load v1 to grab a real gold move
    v1 = load_l2_gold("v1")
    # Pick the first entry and craft a mock that returns its gold move at top-1.
    target_entry = v1[0]
    fixed = AnalysisResult(
        engine_id="stockfish",
        engine_version="fake",
        fen=target_entry.fen,
        depth_reached=15,
        multipv=1,
        settings_hash="fake",
        cpu_arch="fake",
        thread_count=1,
        pvs=[
            PVLine(
                moves=[target_entry.best_move_uci],
                score=Score(kind="cp", value=target_entry.score_cp),
                depth=15,
                multipv=1,
            ),
        ],
    )
    mock_pool = MagicMock()
    mock_pool.analyze = AsyncMock(return_value=fixed)

    # Construct a SINGLE-position in-memory corpus with just the first entry,
    # then mock load_l2_gold to return it. Use monkeypatch for cleanest test.
    from chess_coach.gateway.routes import eval_verifier as ev_mod
    monkeypatched = [target_entry]
    original_loader = ev_mod.load_l2_gold
    ev_mod.load_l2_gold = lambda *a, **kw: monkeypatched  # type: ignore
    try:
        results = await verify_corpus(CorpusVersion.V1, pool=mock_pool, depth=15, top_n=3)
        assert len(results) == 1
        r = results[0]
        assert r.id == target_entry.id
        assert r.status == "match_top1"
        assert r.delta_cp == 0  # mock returned gold's exact score
    finally:
        ev_mod.load_l2_gold = original_loader


def test_verify_corpus_unknown_version_raises():
    import pytest
    # CorpusVersion is a strict enum; passing "v3" raises out of the gate.
    with pytest.raises((ValueError, KeyError, TypeError)):
        # mypy doesn't know about the enum's behavior here; use a static check
        CorpusVersion("v3")
