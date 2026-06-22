"""Grounded narration pipeline: prompt → LLM → validate → retry/fallback.

Uses multi-turn conversation on retry: the failed narration is fed back as an
assistant turn, and the correction instruction arrives as a user turn.  This
preserves system-prompt authority while giving the model direct recency-weight.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass

from chess_coach.protocol_types.analysis import AnalysisResult
from chess_coach.llm_router.router import LLMRouter, LLMUnavailableError
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
    """
    narration: str
    pv_moves: list[str]
    score_display: str


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
    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or LLMRouter()

    async def explain(self, result: AnalysisResult) -> str:
        """Return a narration string (always succeeds)."""
        user_prompt = build_user_prompt(result)
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
                validation = validate_citations(narration, result)
                if validation.valid:
                    return narration

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
                last_error = "; ".join(error_parts)
                last_narration = narration
                logger.debug("Attempt %d failed validation: %s", attempt, last_error)
            except LLMUnavailableError:
                logger.warning("LLM unavailable — returning template fallback")
                return _template_fallback(result)

        logger.warning("%d attempts exhausted — returning template fallback", MAX_ATTEMPTS)
        return _template_fallback(result)

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
        text = await self.explain(result)
        pv_moves, score_display = _format_pv_fields(result)
        return NarrationOutput(narration=text, pv_moves=pv_moves, score_display=score_display)

