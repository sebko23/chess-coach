"""Unit tests for the grounded-narration pipeline."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock

from chess_coach.protocol_types.analysis import AnalysisResult, PVLine, Score
from chess_coach.narration.pipeline import NarrationPipeline
from chess_coach.narration.validator import (
    validate_citations,
    _normalize_move,
    _parse_eval_tag,
)
from chess_coach.llm_router.router import LLMUnavailableError

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _analysis_result(pv_moves=None, score_cp=38):
    if pv_moves is None:
        pv_moves = ["e2e4", "e7e5"]
    return AnalysisResult(
        engine_id="sf",
        engine_version="Stockfish 18",
        fen=START_FEN,
        depth_reached=8,
        multipv=1,
        settings_hash="abc",
        cpu_arch="x86_64",
        thread_count=1,
        pvs=[
            PVLine(
                multipv=1,
                score=Score(kind="cp", value=score_cp),
                depth=8,
                moves=pv_moves,
            )
        ],
    )


class TestParseEvalTag:
    """Tests for _parse_eval_tag — the regex-based eval parser."""

    def test_parse_cp_float(self):
        assert _parse_eval_tag("+0.38") == ("cp", 38)

    def test_parse_cp_negative(self):
        assert _parse_eval_tag("-1.25") == ("cp", -125)

    def test_parse_cp_whole_number(self):
        assert _parse_eval_tag("2") == ("cp", 200)

    def test_parse_mate_hash(self):
        assert _parse_eval_tag("#2") == ("mate", 2)

    def test_parse_mate_negative_hash(self):
        assert _parse_eval_tag("#-3") == ("mate", -3)

    def test_parse_mate_in_word_form(self):
        assert _parse_eval_tag("mate in 2") == ("mate", 2)

    def test_parse_mate_in_word_form_negative(self):
        assert _parse_eval_tag("mate in -1") == ("mate", -1)

    def test_parse_mate_in_case_insensitive(self):
        assert _parse_eval_tag("Mate In 3") == ("mate", 3)

    def test_parse_unparseable(self):
        assert _parse_eval_tag("blah") is None

    def test_parse_empty(self):
        assert _parse_eval_tag("") is None


class TestValidator:
    def test_move_normalization_correct_san(self):
        norm = _normalize_move(START_FEN, "e4")
        assert norm == "e2e4"

    def test_move_normalization_handles_capture_notation(self):
        board = "r1bqkbnr/1ppp1ppp/p1B5/4p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 0 4"
        norm = _normalize_move(board, "Nf6")
        assert norm == "g8f6"

    def test_normalization_unparseable(self):
        norm = _normalize_move(START_FEN, "Xx9")
        assert norm is None

    def test_validate_happy_path(self):
        result = _analysis_result()
        narration = "Stockfish sees <eval>+0.38</eval> and suggests <move>e4</move>."
        vr = validate_citations(narration, result)
        assert vr.valid

    def test_validate_hallucinated_move(self):
        result = _analysis_result(pv_moves=["e2e4", "e7e5"])
        narration = "Best is <move>Qh5</move>."
        vr = validate_citations(narration, result)
        assert not vr.valid
        assert "Qh5" in vr.missing_moves

    def test_validate_notation_variant_still_valid(self):
        result = _analysis_result(pv_moves=["e2e4", "e7e5"])
        narration = "Play <move>e4</move> with eval <eval>+0.38</eval>."
        vr = validate_citations(narration, result)
        assert vr.valid

    def test_validate_eval_outside_tolerance(self):
        result = _analysis_result(score_cp=38)
        narration = "Eval is <eval>+0.80</eval>."
        vr = validate_citations(narration, result)
        assert not vr.valid
        assert "+0.80" in vr.missing_evals

    def test_validate_mate_position(self):
        result = AnalysisResult(
            engine_id="sf",
            engine_version="SF 18",
            fen=START_FEN,
            depth_reached=10,
            multipv=1,
            settings_hash="x",
            cpu_arch="x86_64",
            thread_count=1,
            pvs=[
                PVLine(
                    multipv=1,
                    score=Score(kind="mate", value=2),
                    depth=10,
                    moves=["e2e4", "e7e5", "d1h5"],
                )
            ],
        )
        narration = "Mate in <eval>#2</eval> with <move>e4</move>."
        vr = validate_citations(narration, result)
        assert vr.valid

    def test_validate_mate_in_two_word_form(self):
        """mate in 2 word form should also pass validation."""
        result = AnalysisResult(
            engine_id="sf",
            engine_version="SF 18",
            fen=START_FEN,
            depth_reached=10,
            multipv=1,
            settings_hash="x",
            cpu_arch="x86_64",
            thread_count=1,
            pvs=[
                PVLine(
                    multipv=1,
                    score=Score(kind="mate", value=2),
                    depth=10,
                    moves=["e2e4", "e7e5", "d1h5"],
                )
            ],
        )
        narration = "Mate in <eval>mate in 2</eval> with <move>e4</move>."
        vr = validate_citations(narration, result)
        assert vr.valid


async def _make_router(responses: list[str]) -> MagicMock:
    router = MagicMock()
    router.complete = AsyncMock(side_effect=responses)
    return router


class TestNarrationPipeline:
    async def test_happy_path(self):
        result = _analysis_result()
        router = await _make_router(["Try <move>e4</move> with eval <eval>+0.38</eval>."])
        pipeline = NarrationPipeline(router=router)
        narration = await pipeline.explain(result)
        assert "e4" in narration
        router.complete.assert_called_once()

    async def test_hallucinated_move_retries_then_fallback(self):
        result = _analysis_result(pv_moves=["e2e4"])
        responses = [
            "The move <move>Qh5</move> is strong with eval <eval>+1.0</eval>.",
            "Better is <move>Qh5</move> with eval <eval>+0.90</eval>.",
            "Consider <move>Qh5</move> with eval <eval>+0.80</eval>.",
        ]
        router = await _make_router(responses)
        pipeline = NarrationPipeline(router=router)
        narration = await pipeline.explain(result)
        assert "Stockfish evaluates" in narration
        assert router.complete.call_count == 3

    async def test_notation_variant_passes(self):
        result = _analysis_result(pv_moves=["e2e4", "e7e5"])
        router = await _make_router(["Try <move>e4</move> with eval <eval>+0.38</eval>."])
        pipeline = NarrationPipeline(router=router)
        narration = await pipeline.explain(result)
        assert "e4" in narration

    async def test_llm_unavailable_error_fallback(self):
        result = _analysis_result()
        router = MagicMock()
        router.complete = AsyncMock(side_effect=LLMUnavailableError("primary down"))
        pipeline = NarrationPipeline(router=router)
        narration = await pipeline.explain(result)
        assert "Stockfish evaluates" in narration
        assert router.complete.call_count == 1

    async def test_mate_narration_fallback_includes_mate(self):
        result = AnalysisResult(
            engine_id="sf",
            engine_version="SF 18",
            fen=START_FEN,
            depth_reached=10,
            multipv=1,
            settings_hash="x",
            cpu_arch="x86_64",
            thread_count=1,
            pvs=[
                PVLine(
                    multipv=1,
                    score=Score(kind="mate", value=2),
                    depth=10,
                    moves=["e2e4", "e7e5", "d1h5"],
                )
            ],
        )
        router = MagicMock()
        router.complete = AsyncMock(side_effect=LLMUnavailableError("down"))
        pipeline = NarrationPipeline(router=router)
        narration = await pipeline.explain(result)
        assert "mate" in narration.lower()


class TestExplainSimple:
    """Tests for NarrationPipeline.explain_simple() — the route-facing wrapper."""

    async def test_explain_simple_positive_eval(self):
        router = await _make_router(["Nice central control."])
        pipeline = NarrationPipeline(router=router)
        result = await pipeline.explain_simple(
            fen=START_FEN, move_san="e4", eval_cp=38
        )
        assert result.score_display == "+0.38"
        assert result.pv_moves == []
        assert "Nice central control." in result.narration

    async def test_explain_simple_negative_eval(self):
        router = await _make_router(["Tough position."])
        pipeline = NarrationPipeline(router=router)
        result = await pipeline.explain_simple(
            fen=START_FEN, eval_cp=-125
        )
        assert result.score_display == "-1.25"
        assert result.pv_moves == []

    async def test_explain_simple_without_eval_cp(self):
        router = await _make_router(["Interesting structure."])
        pipeline = NarrationPipeline(router=router)
        result = await pipeline.explain_simple(fen=START_FEN, eval_cp=None)
        assert result.score_display == "+0.00"
        assert not result.narration.startswith("Stockfish evaluates")

    async def test_explain_simple_llm_unavailable_returns_template(self):
        router = await _make_router([LLMUnavailableError("no LLM")])
        pipeline = NarrationPipeline(router=router)
        result = await pipeline.explain_simple(
            fen=START_FEN, eval_cp=50
        )
        assert result.narration.startswith("Stockfish evaluates")
        assert result.score_display == "+0.50"
        assert result.pv_moves == []
