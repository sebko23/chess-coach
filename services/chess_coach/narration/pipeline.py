"""Grounded narration pipeline: prompt → LLM → validate → retry/fallback."""
from __future__ import annotations
import logging

from chess_coach.protocol_types.analysis import AnalysisResult
from chess_coach.llm_router.router import LLMRouter, LLMUnavailableError
from .prompt import SYSTEM_PROMPT, build_user_prompt
from .validator import validate_citations

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


def _template_fallback(result: AnalysisResult) -> str:
    if not result.pvs:
        return "No analysis lines available."
    pv = result.pvs[0]
    if pv.score.kind == "mate":
        score_str = f"mate in {pv.score.value}"
    else:
        score_str = f"{pv.score.value / 100:+.2f}"
    moves_str = " ".join(pv.moves[:6])
    return (
        f"Stockfish evaluates this position as {score_str}."
        f" The best continuation is {moves_str}."
    )


class NarrationPipeline:
    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or LLMRouter()

    async def explain(self, result: AnalysisResult) -> str:
        user_prompt = build_user_prompt(result)
        last_narration: str | None = None
        last_error: str | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                extra = ""
                if last_narration is not None and last_error:
                    extra = (
                        f"\n\nCORRECTION REQUIRED (attempt {attempt}/{MAX_ATTEMPTS}): "
                        f"Your previous response failed validation because: {last_error}. "
                        f"Revise your narration to cite only the moves listed above."
                    )
                narration = await self._router.complete(
                    system=SYSTEM_PROMPT,
                    user=user_prompt + extra,
                )
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
