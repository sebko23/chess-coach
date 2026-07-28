"""Grounded narration pipeline: prompt → LLM → validate → retry/fallback.

Uses multi-turn conversation on retry: the failed narration is fed back as an
assistant turn, and the correction instruction arrives as a user turn.  This
preserves system-prompt authority while giving the model direct recency-weight.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from chess_coach.llm_router.router import LLMRouter, LLMUnavailableError
from chess_coach.protocol_types.analysis import AnalysisResult

from .grounding import GroundingIndex, build_grounding_block
from .prompt import SYSTEM_PROMPT, build_user_prompt
from .validator import validate_citations

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3

def _format_pv_fields(result: AnalysisResult) -> tuple[list[str], str]:
    """Return (pv_moves, score_display) extracted from the first PV line."""
    if not result.pvs:
        return [], ""
    pv = result.pvs[0]
    if pv.score.kind == "mate":
        score_str = f"mate in {pv.score.value}"
    else:
        score_str = f"{pv.score.value / 100:+.2f}"
    return list(pv.moves[:6]), score_str


def _template_fallback(result: AnalysisResult) -> str:
    if not result.pvs:
        return "No analysis lines available."
    moves, score = _format_pv_fields(result)
    moves_str = " ".join(moves)
    return (
        f"Stockfish evaluates this position as {score}."
        f" The best continuation is {moves_str}."
    )


@dataclass(frozen=True)
class NarrationOutput:
    """Structured result of a grounded narration.

    narration: LLM narration string (or template fallback if LLM failed).
    pv_moves: principal variation moves in SAN, up to 6 plies.
    score_display: formatted score ("+0.30", "mate in 3", or "").
    corpus_entry_id: The v2 narrative corpus entry (NG-v2-NNNN) whose
        narrative_explanation was used to ground the narration, or
        None if no FEN match in the corpus (no grounding block
        injected). Used by the route for the audit table.
    """

    narration: str
    pv_moves: list[str]
    score_display: str
    corpus_entry_id: str | None = None

def _build_correction_prompt(last_error: str) -> str:
    """Build the correction instruction for retry attempts.

    Explicitly tells the model WHY the validation failed and forbids
    the most common failure modes: averaging scores, inventing moves.
    """
    return (
        f"Your previous response failed validation because: {last_error}. "
        "Revise your narration. RULES:\n"
        "- Cite only moves that appear EXACTLY in the ENGINE ANALYSIS above.\n"
        "- Cite a score exactly as provided — do NOT average, interpolate, "
        "round, or summarise evaluations across lines.\n"
        "- Do not invent moves, lines, or variations not present in the "
        "analysis.\n"
        "- Keep the narration under 150 words."
    )


class NarrationPipeline:
    def __init__(
        self,
        router: LLMRouter | None = None,
        grounding: GroundingIndex | None = None,
    ) -> None:
        """Initialize the narration pipeline.

        `grounding` is optional; when None, no v2 corpus lookup
        happens and the pipeline behaves exactly as before BBF-87.1
        (no `<grounding>` tags, no FEN-keyed block injection).
        Production code passes a GroundingIndex built from the v2
        corpus; tests can pass None to exercise the no-grounding
        path or a tmp-path-loaded index to exercise the grounding path.
        """
        self._router = router or LLMRouter()
        self._grounding = grounding

    async def explain(self, result: AnalysisResult) -> tuple[str, str | None]:
        """Return (narration, corpus_entry_id).

        The narration string is always non-empty (falls back to
        template on LLM failure or after MAX_ATTEMPTS). The
        corpus_entry_id is the v2 entry that grounded this
        narration, or None if no FEN match.
        """
        # BBF-87.1: look up the FEN in the v2 corpus. The
        # grounding block is prepended to the user prompt so the
        # LLM sees it before the engine analysis.
        match = (
            self._grounding.lookup(result.fen)
            if self._grounding is not None
            else None
        )
        grounding_block = build_grounding_block(match)
        user_prompt = build_user_prompt(
            result, grounding_block=grounding_block,
        )
        corpus_entry_id = match.entry_id if match else None
        last_narration: str | None = None
        last_error: str | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                messages: list[dict[str, str]] = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                ]
                if last_narration is not None and last_error:
                    # Multi-turn correction: assistant turn with failed output,
                    # then user turn with explicit correction instruction.
                    messages.append(
                        {"role": "user", "content": user_prompt}
                    )
                    messages.append(
                        {"role": "assistant", "content": last_narration}
                    )
                    messages.append(
                        {"role": "user", "content": _build_correction_prompt(last_error)}
                    )
                else:
                    # First attempt: simple system + user.
                    messages.append(
                        {"role": "user", "content": user_prompt}
                    )

                narration = await self._router.complete(messages)
                validation = validate_citations(
                    narration, result, grounding_match=match,
                )
                if validation.valid:
                    return narration, corpus_entry_id

                error_parts: list[str] = []
                if validation.missing_moves:
                    error_parts.append(
                        f"Cited moves not in analysis: {', '.join(validation.missing_moves)}"
                    )
                if validation.missing_evals:
                    error_parts.append(
                        f"Cited evaluations not in analysis: {', '.join(validation.missing_evals)}"
                    )
                if validation.bad_notation:
                    error_parts.append(
                        f"Unparseable or incorrect moves: "
                        f"{', '.join(b[0] + ' (' + b[1] + ')' for b in validation.bad_notation)}"
                    )
                if validation.grounding_failures:
                    error_parts.append(
                        f"Grounding citations not in matched corpus "
                        f"entry: {', '.join(validation.grounding_failures)}"
                    )
                last_error = "; ".join(error_parts)
                last_narration = narration
                logger.debug("Attempt %d failed validation: %s", attempt, last_error)
            except LLMUnavailableError:
                logger.warning("LLM unavailable — returning template fallback")
                return _template_fallback(result), corpus_entry_id

        logger.warning("%d attempts exhausted — returning template fallback", MAX_ATTEMPTS)
        return _template_fallback(result), corpus_entry_id

    async def explain_simple(
        self,
        fen: str,
        move_san: str | None = None,
        eval_cp: int | None = None,
        game_phase: str | None = None,
        context: str | None = None,
    ) -> NarrationOutput:
        """Convenience wrapper for the route handler.

        Builds a minimal AnalysisResult from simple user inputs and
        delegates to the full explain() pipeline with LLM + validation.

        Returns a NarrationOutput. The `corpus_entry_id` is populated
        when the FEN matched a v2 corpus entry (BBF-87.1).
        """
        from chess_coach.protocol_types.analysis import PVLine, Score

        pvs = []
        if eval_cp is not None:
            pvs.append(PVLine(
                multipv=1,
                score=Score(kind="cp", value=eval_cp),
                depth=1,
                moves=[],
                nodes=0,
                time_ms=0,
                nps=None,
            ))
        else:
            # Synthetic neutral PVLine -- preserves AnalysisResult.pvs
            # min_length=1 invariant when the route caller didn't supply
            # eval_cp. Formatter already handles empty moves gracefully.
            pvs.append(PVLine(
                multipv=1,
                score=Score(kind="cp", value=0),
                depth=1,
                moves=[],
                nodes=None,
                time_ms=None,
                nps=None,
            ))

        result = AnalysisResult(
            engine_id="user-request",
            engine_version="n/a",
            fen=fen,
            depth_reached=1,
            multipv=1,
            settings_hash="",
            cpu_arch="unknown",
            thread_count=1,
            pvs=pvs,
        )
        text, corpus_entry_id = await self.explain(result)
        pv_moves, score_display = _format_pv_fields(result)
        return NarrationOutput(
            narration=text,
            pv_moves=pv_moves,
            score_display=score_display,
            corpus_entry_id=corpus_entry_id,
        )

