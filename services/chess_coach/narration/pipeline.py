"""Grounded narration pipeline: prompt → LLM → validate → retry/fallback.

Uses multi-turn conversation on retry: the failed narration is fed back as an
assistant turn, and the correction instruction arrives as a user turn.  This
preserves system-prompt authority while giving the model direct recency-weight.

Scope of validation (BBF-86 external-review F3):

  This pipeline validates **citation correctness** — cited moves appear in
  the engine PV, cited evaluations match the engine score (exact mate or
  centipawn ±20), and <grounding> tags map back to the matched v2 corpus
  entry by word-LCS similarity (see services/chess_coach/narration/validator.py:
  the validator emits a structured `validations.missing_moves /
  missing_evals / bad_notation / grounding_failures` shape). It does NOT
  validate **LLM output quality** — narrative fluency, factual accuracy
  beyond cited tags, and pedagogical value are out of scope for the
  validator; the validator deliberately consumes only the citation shape.

  Test surface:

  - tests/integration/test_narrative_pipeline_grounded.py drives the
    full HTTP path with a stub LLMRouter returning a pre-canned
    narration. **The stub's citations do NOT match the synthetic route
    analysis PVs** (see the test's own comments at lines 122-130), so
    validation is expected to fail and `grounded` may be False there;
    the test asserts only the audit-table contract
    (`corpus_entry_id` populated / NULL), NOT the citation-validation
    outcome. Callers should not infer "the LLM produces valid citations"
    from this test.

  - tests/unit/test_narrative_grounding.py exercises the validator's
    word-LCS similarity path DIRECTLY (no stub router, no LLM).
    Tokens, LCS counts, and `_grounding_similarity_ok` thresholds are
    asserted at the function level.

  - tests/unit/test_narration.py exercises the prompt-format and
    pipeline retry loop.

  Production deployments currently use the LLMRouter with OpenRouter
  (primary + fallback) via services/chess_coach/llm_router/router.py;
  an absent key raises LLMUnavailableError and the pipeline returns
  the template fallback at services/chess_coach/narration/pipeline.py.
  The citation validator runs the same way on real LLM output as it
  would on a stub. Real-LLM integration + LLM-quality validation are
  held back as separate work items (see v2 handoff §13.3 Tier 4 #15).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from chess_coach.llm_router.router import LLMRouter, LLMUnavailableError
from chess_coach.protocol_types.analysis import AnalysisResult

from .grounding import GroundingIndex, build_grounding_block
from .prompt import SYSTEM_PROMPT, build_user_prompt
from .validator import validate_citations

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


def _pv_to_san(fen: str, uci_moves: list[str]) -> list[str]:
    """Convert a UCI principal variation to SAN, one SAN per UCI move.

    FU-5: human-display-only translation for the frontend's "Best Line" /
    "Engine line" rendering. UCI stays authoritative on the wire per
    specs/v1.0/chess-coach-protocol-v1.md:42 ("SAN may be returned as
    an additional field for human display but is never authoritative").

    SAN is position-dependent: each successive SAN move needs the board
    state *after* the prior UCI is applied, not the starting FEN. Naive
    per-move ``Board(fen).san(uci)`` emits broken SAN for any move where
    file disambiguation depends on earlier moves (e.g. ``b8c6`` after
    a knights-only position — naive emits ``Nxc6``, replay emits ``Nc6``).

    Build a single ``chess.Board(fen)`` and apply each UCI in order,
    recording ``board.san(move)`` from the pre-push state.

    Error semantics: never raise. On any per-move failure (bad FEN,
    malformed UCI string, illegal-in-position move, missing promotion
    suffix), fall back to the UCI string for that move and log a warning.
    UCI is the authoritative wire format; silent fallback preserves the
    list-length invariant and keeps the response parseable when python-chess
    cannot resolve an unusual PV entry. ``chess`` is imported lazily so
    tests that never call this function don't pay the import cost.

    Returns a list aligned 1:1 with ``uci_moves`` (same length).
    """
    try:
        import chess  # noqa: PLC0415 - lazy import; python-chess is a dep
        # but avoid loading it on every test that imports pipeline.
    except ImportError:
        logger.warning(
            "_pv_to_san: python-chess not available; returning UCI verbatim"
        )
        return list(uci_moves)
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        logger.warning(
            "_pv_to_san: invalid FEN (%s); returning UCI verbatim", exc,
        )
        return list(uci_moves)
    out: list[str] = []
    for uci in uci_moves:
        try:
            move = chess.Move.from_uci(uci)
        except (ValueError, chess.InvalidMoveError) as exc:
            logger.warning(
                "_pv_to_san: malformed UCI %r (%s); falling back to UCI",
                uci, exc,
            )
            out.append(uci)
            continue
        # board.legal_membership is the canonical way to check
        # legal-shape-but-illegal-in-position; board.san also raises
        # ValueError on the same case, but checking membership first
        # gives a cleaner log message.
        if move not in board.legal_moves:
            logger.warning(
                "_pv_to_san: UCI %r not legal in current position; "
                "falling back to UCI", uci,
            )
            out.append(uci)
            continue
        try:
            san = board.san(move)
        except ValueError as exc:
            logger.warning(
                "_pv_to_san: board.san(%r) raised %s; falling back to UCI",
                uci, exc,
            )
            out.append(uci)
            continue
        out.append(san)
        # Apply the move so the next SAN sees the post-move board state.
        board.push(move)
    return out


def _format_pv_fields(
    result: AnalysisResult,
) -> tuple[list[str], list[str], str]:
    """Return (pv_moves_uci, pv_moves_san, score_display) from the first PV.

    FU-5: extended to also return the SAN translation. UCI stays
    authoritative on the wire; SAN is purely for human display. Both
    lists are sliced to the same first-6-plies window so callers can
    index them 1:1.
    """
    if not result.pvs:
        return [], [], ""
    pv = result.pvs[0]
    if pv.score.kind == "mate":
        score_str = f"mate in {pv.score.value}"
    else:
        score_str = f"{pv.score.value / 100:+.2f}"
    uci_list = list(pv.moves[:6])
    san_list = _pv_to_san(result.fen, uci_list)
    return uci_list, san_list, score_str


def _template_fallback(result: AnalysisResult) -> str:
    if not result.pvs:
        return "No analysis lines available."
    _uci_moves, san_moves, score = _format_pv_fields(result)
    moves_str = " ".join(san_moves)
    return (
        f"Stockfish evaluates this position as {score}."
        f" The best continuation is {moves_str}."
    )


@dataclass(frozen=True)
class NarrationOutput:
    """Structured result of a grounded narration.

    narration: LLM narration string (or template fallback if LLM failed).
    pv_moves: principal variation moves in UCI (e.g. ['e2e4', 'e7e5']),
        up to 6 plies. Authoritative on the wire per
        specs/v1.0/chess-coach-protocol-v1.md:42.
    pv_moves_san: same PV moves in SAN (e.g. ['e4', 'e5', 'Nf3']), up to
        6 plies. Human-display-only. Falls back to the UCI string per
        move if the SAN conversion fails for that move. Length is always
        aligned 1:1 with pv_moves. Default empty list for legacy
        callers; the route always populates it.
    score_display: formatted score ("+0.30", "mate in 3", or "").
    corpus_entry_id: The v2 narrative corpus entry (NG-v2-NNNN) whose
        narrative_explanation was used to ground the narration, or
        None if no FEN match in the corpus (no grounding block
        injected). Used by the route for the audit table.
    """

    narration: str
    pv_moves: list[str]
    score_display: str
    pv_moves_san: list[str] = field(default_factory=list)
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
        eval_cp: int | None = None,
    ) -> NarrationOutput:
        """Convenience wrapper for the route handler.

        Builds a minimal AnalysisResult from `fen` (required) and
        optional `eval_cp` (consumed to construct the synthetic
        AnalysisResult.pvs[0].score). Per FU-8 (2026-08-10): the
        prior signature also accepted `move_san`, `game_phase`, and
        `context`; those parameters were collected at the route
        boundary but never referenced in this function body, so they
        were dead plumbing that existed "safe by accident." If a
        future feature needs user-context plumbing into the LLM
        prompt, it should be designed with sanitization built in from
        the start (security-strategy.md §A-F12) rather than
        resurrected from this dead code.

        Delegates to the full explain() pipeline with LLM + validation.
        Returns a NarrationOutput. The `corpus_entry_id` is populated
        when the FEN matched a v2 corpus entry (BBF-87.1). The
        `pv_moves_san` field is populated alongside `pv_moves` (FU-5).
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
        pv_moves_uci, pv_moves_san, score_display = _format_pv_fields(result)
        return NarrationOutput(
            narration=text,
            pv_moves=pv_moves_uci,
            pv_moves_san=pv_moves_san,
            score_display=score_display,
            corpus_entry_id=corpus_entry_id,
        )
