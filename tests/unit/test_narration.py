"""Unit tests for the grounded-narration pipeline."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from chess_coach.llm_router.router import LLMUnavailableError
from chess_coach.narration.pipeline import NarrationPipeline
from chess_coach.narration.validator import (
    _normalize_move,
    _parse_eval_tag,
    validate_citations,
)
from chess_coach.protocol_types.analysis import AnalysisResult, PVLine, Score

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
        # BBF-87.1: explain() now returns (narration, corpus_entry_id).
        narration, corpus_entry_id = await pipeline.explain(result)
        assert "e4" in narration
        assert corpus_entry_id is None  # no FEN in v2 corpus
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
        narration, _ = await pipeline.explain(result)
        assert "Stockfish evaluates" in narration
        assert router.complete.call_count == 3

    async def test_notation_variant_passes(self):
        result = _analysis_result(pv_moves=["e2e4", "e7e5"])
        router = await _make_router(["Try <move>e4</move> with eval <eval>+0.38</eval>."])
        pipeline = NarrationPipeline(router=router)
        narration, _ = await pipeline.explain(result)
        assert "e4" in narration

    async def test_llm_unavailable_error_fallback(self):
        result = _analysis_result()
        router = MagicMock()
        router.complete = AsyncMock(side_effect=LLMUnavailableError("primary down"))
        pipeline = NarrationPipeline(router=router)
        narration, _ = await pipeline.explain(result)
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
        narration, _ = await pipeline.explain(result)
        assert "mate" in narration.lower()


class TestExplainSimple:
    """Tests for NarrationPipeline.explain_simple() — the route-facing wrapper."""

    async def test_explain_simple_positive_eval(self):
        router = await _make_router(["Nice central control."])
        pipeline = NarrationPipeline(router=router)
        # FU-8: explain_simple signature no longer accepts move_san.
        # Previously this test passed move_san="e4" even though the
        # param was never used -- exercising the dead plumbing.
        result = await pipeline.explain_simple(
            fen=START_FEN, eval_cp=38
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

class TestFU8DeadPlumbingRemoved:
    """FU-8: dead-code narration-context plumbing removal.

    Verifies that the LLM-facing prompt construction surface has
    no route for arbitrary user-controlled text to reach it. The
    removed plumbing was:
      - prompt_context constructed at the route boundary
        (services/chess_coach/gateway/routes/narration.py)
      - context, move_san, game_phase parameters on
        pipeline.explain_simple()
        (services/chess_coach/narration/pipeline.py)
      - body.context user-supplied free-form text + sanitization
        call site at the route boundary

    Per FU-8 entry, the dead plumbing was "safe by accident":
    the sanitized string was silently dropped before reaching the
    LLM prompt. These tests assert the SURFACE ITSELF is gone, not
    just that the current code happens to not call it. Any future
    addition that re-introduces a route for user-controlled text
    into the LLM prompt will fail one of these tests; failure
    messages point to the sanitization pipeline that would need to
    be exercised end-to-end before re-introduction.
    """

    # Sanitization-pipeline context for failure messages. Reused as
    # a constant so any single-point edit propagates to all tests.
    _SANITIZE_REF = (
        "Per FU-8 (docs/16_audit/OPEN-FOLLOWUPS.md FU-8 entry): the\n"
        "removed plumbing collected body.context user-supplied\n"
        "free-form text and called sanitize_user_content at the\n"
        "route boundary, but the sanitized string was silently\n"
        "dropped before reaching the LLM prompt. If you are\n"
        "re-introducing this parameter, the sanitization pipeline\n"
        "(services/chess_coach/narration/sanitize.py + security-\n"
        "strategy.md section A-F12) MUST be exercised end-to-end\n"
        "before re-adding -- not just on the call site, but with\n"
        "a test that asserts the sanitization flows through to the\n"
        "LLM prompt. Also confirm with project lead (per 7.1) that\n"
        "context-aware narration is actually a desired feature before\n"
        "re-introducing the plumbing."
    )

    def test_explain_simple_signature_has_no_user_context_params(self):
        """explain_simple() must not accept user-controlled context fields."""
        import inspect
        params = list(inspect.signature(NarrationPipeline.explain_simple).parameters.keys())
        # eval_cp is the only user-context-style param that should remain
        # (it feeds the synthetic PVLine). The others are dead per FU-8.
        forbidden = ("move_san", "game_phase", "context")
        leaked = [p for p in forbidden if p in params]
        assert not leaked, (
            "explain_simple() still accepts " + str(leaked)
            + " -- should be removed per FU-8 (dead plumbing,\n"
            "safe-by-accident surface).\n" + self._SANITIZE_REF
        )

    def test_build_user_prompt_signature_has_no_user_context_params(self):
        """build_user_prompt() must not accept user-controlled context fields."""
        import inspect
        from chess_coach.narration.prompt import build_user_prompt
        params = list(inspect.signature(build_user_prompt).parameters.keys())
        forbidden = ("context", "user_context", "prompt_context")
        leaked = [p for p in forbidden if p in params]
        assert not leaked, (
            "build_user_prompt() still accepts " + str(leaked)
            + " -- user-controlled text has no route into the\n"
            "prompt construction per FU-8.\n" + self._SANITIZE_REF
        )

    def test_format_analysis_for_prompt_only_uses_analysis_result(self):
        """format_analysis_for_prompt() must take only AnalysisResult."""
        import inspect
        from chess_coach.narration.prompt import format_analysis_for_prompt
        params = list(inspect.signature(format_analysis_for_prompt).parameters.keys())
        assert params == ["result"], (
            "format_analysis_for_prompt() params are " + str(params)
            + "; expected only [result]. Any additional param\n"
            "is a potential user-controlled-text injection vector\n"
            "into the LLM prompt.\n" + self._SANITIZE_REF
        )

    def test_route_does_not_construct_prompt_context(self):
        """The narration route must not construct prompt_context or context_parts.

        Uses AST (not raw source-text scan) so the FU-8 marker
        comment in the route module documenting this removal is
        not itself counted as a "leaked" identifier. The marker
        is checked separately by test_route_has_fu8_marker_comment.
        """
        import ast
        import inspect
        from chess_coach.gateway.routes import narration
        src = inspect.getsource(narration)
        tree = ast.parse(src)
        # Walk all identifier names referenced in actual code (Name +
        # Attribute contexts). Comments and docstrings are excluded
        # because they are not executable code.
        code_identifiers = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                code_identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                code_identifiers.add(node.attr)
        forbidden = ("prompt_context", "context_parts")
        leaked = [i for i in forbidden if i in code_identifiers]
        assert not leaked, (
            str(leaked) + " still referenced as code in narration\n"
            "route -- dead plumbing should be removed per FU-8.\n"
            "(Note: the FU-8 marker comment in the route docstring\n"
            "mentions these identifiers by name; that is expected\n"
            "and is checked by test_route_has_fu8_marker_comment.\n"
            "This test only flags executable code references.)\n"
            + self._SANITIZE_REF
        )

    def test_route_does_not_sanitize_user_content(self):
        """The narration route must not call sanitize_user_content.

        The sanitize_user_content function itself remains in the
        library (services/chess_coach/narration/sanitize.py) for
        future use when context-aware narration is properly designed.
        But the call site that fed the dead prompt_context plumbing
        should be gone.
        """
        from chess_coach.gateway.routes import narration
        import inspect
        src = inspect.getsource(narration)
        assert b"sanitize_user_content" not in src.encode(), (
            "sanitize_user_content still called in narration route\n"
            "-- the sanitization that fed the dropped prompt_context\n"
            "should be removed too (the call site, not the library\n"
            "function).\n" + self._SANITIZE_REF
        )

    def test_route_has_fu8_marker_comment(self):
        """Route must have an FU-8 marker comment linking to the decision.

        Regression guard beyond signatures/source-checks: a future
        refactor that removes the FU-8 explanatory comment would lose
        the rationale context for why this plumbing was removed.
        This test catches that drift and points back to the FU-8
        entry in OPEN-FOLLOWUPS.md.
        """
        from chess_coach.gateway.routes import narration
        import inspect
        src = inspect.getsource(narration)
        assert "FU-8" in src, (
            "narration route module has no FU-8 marker comment.\n"
            "If the comment was accidentally removed during a refactor,\n"
            "restore it -- it documents the rationale for the dead\n"
            "plumbing removal (see docs/16_audit/OPEN-FOLLOWUPS.md FU-8)."
        )
