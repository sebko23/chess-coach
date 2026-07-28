"""Citation extraction and ground-truth validation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from chess_coach.protocol_types.analysis import AnalysisResult, Score

try:
    import chess
except ImportError:
    chess = None  # type: ignore[assignment]

_MOVE_RE = re.compile(r"<move>([^<]+)</move>")
_EVAL_RE = re.compile(r"<eval>([^<]+)</eval>")
_GROUNDING_RE = re.compile(r"<grounding>([^<]+)</grounding>")
_MATE_RE = re.compile(r"^(?:#|mate\s+in\s+)(-?\d+)$", re.IGNORECASE)
EVAL_TOLERANCE_CP = 20  # ±0.20 pawns
# BBF-87.1: grounding citations are accepted when the longest
# common substring between the citation and the matched corpus
# entry's narrative_explanation meets one of:
#   - >= 30 words, OR
#   - >= 50% of the citation's word count.
# These thresholds are heuristic (full semantic comparison is
# out of scope). They allow the LLM to rephrase moderately
# without failing the citation check.
GROUNDING_MIN_LCS_WORDS = 30
GROUNDING_MIN_OVERLAP_RATIO = 0.5


@dataclass
class ValidationResult:
    """Result of citation validation."""
    valid: bool = True
    missing_moves: list[str] = field(default_factory=list)
    missing_evals: list[str] = field(default_factory=list)
    bad_notation: list[tuple[str, str]] = field(default_factory=list)
    grounding_failures: list[str] = field(default_factory=list)


def _normalize_move(fen: str, san: str) -> str | None:
    if chess is None:
        return san
    try:
        board = chess.Board(fen)
        move = board.parse_san(san)
        return move.uci()
    except Exception:
        return None


def _parse_eval_tag(raw: str) -> tuple[str, int] | None:
    """Parse an <eval> tag value.

    Returns ("cp", centipawns_int) or ("mate", moves_int) or None if unparseable.
    """
    s = raw.strip()
    # Handle: #2, #-2, mate in 2, mate in -2, M2, Mate in 3
    mate_match = _MATE_RE.match(s)
    if mate_match:
        return ("mate", int(mate_match.group(1)))
    try:
        return ("cp", round(float(s) * 100))
    except ValueError:
        return None


def _collect_ground_truth_moves(result: AnalysisResult) -> set[str]:
    moves: set[str] = set()
    for pv in result.pvs:
        for san in pv.moves:
            norm = _normalize_move(result.fen, san)
            if norm:
                moves.add(norm)
    return moves


def _score_to_tuple(score: Score) -> tuple[str, int]:
    return (score.kind, score.value)


def _word_tokens(text: str) -> list[str]:
    """Lowercased word tokens for similarity checks.

    Splits on whitespace; strips a small set of trailing
    punctuation that the LLM sometimes leaves on quoted text.
    """
    out: list[str] = []
    for tok in text.split():
        # Strip commas/periods that don't change the word
        clean = tok.strip(".,;:!?\"'`()[]")
        if clean:
            out.append(clean.lower())
    return out


def _lcs_word_count(a_words: list[str], b_words: list[str]) -> int:
    """Longest common subsequence of word lists, counted in words.

    Standard O(n*m) DP. The two inputs are the citation's word
    list and the corpus entry's word list; both are short
    (50-200 words), so the DP is fine.
    """
    n, m = len(a_words), len(b_words)
    if n == 0 or m == 0:
        return 0
    # Build DP table (rows = a, cols = b).
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        ai = a_words[i - 1]
        for j in range(1, m + 1):
            if ai == b_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[n][m]


def _grounding_similarity_ok(
    citation_text: str,
    corpus_explanation: str,
) -> bool:
    """True iff the citation has enough word overlap with the
    corpus entry's narrative_explanation to be considered
    a valid quote/paraphrase.

    The check is the longest common subsequence of word lists,
    measured in two ways: an absolute floor (>= 30 words) AND
    a relative floor (>= 50% of the citation's word count).
    Either passing is enough.
    """
    a_words = _word_tokens(citation_text)
    b_words = _word_tokens(corpus_explanation)
    if not a_words:
        # Empty citation is a no-op; the system prompt explicitly
        # says "every quoted sentence must be wrapped", so a
        # citation that's been emptied out fails. We treat
        # empty as failure here (the validator's caller can
        # decide whether to surface this).
        return False
    lcs = _lcs_word_count(a_words, b_words)
    return (
        lcs >= GROUNDING_MIN_LCS_WORDS
        or lcs / max(1, len(a_words)) >= GROUNDING_MIN_OVERLAP_RATIO
    )


def validate_citations(
    narration: str,
    result: AnalysisResult,
    grounding_match: Any = None,
) -> ValidationResult:
    """Validate citations in a narration.

    `grounding_match` (BBF-87.1) is a `GroundingMatch` or None.
    When provided, the validator additionally checks every
    `<grounding>...</grounding>` tag against the matched
    corpus entry's narrative_explanation via a word-LCS
    similarity check. When None, the grounding check is
    skipped (no FEN match -- no grounding block was injected).
    """
    vr = ValidationResult()
    ground_moves = _collect_ground_truth_moves(result)
    ground_scores = [_score_to_tuple(pv.score) for pv in result.pvs]

    # --- move validation ---
    for claimed in _MOVE_RE.findall(narration):
        norm = _normalize_move(result.fen, claimed.strip())
        if norm is None:
            vr.missing_moves.append(claimed.strip())
            vr.bad_notation.append((claimed.strip(), "unparseable SAN"))
        elif norm not in ground_moves:
            vr.missing_moves.append(claimed.strip())
            vr.bad_notation.append((claimed.strip(), f"{norm} not in PV lines"))

    # --- eval validation ---
    for raw_eval in _EVAL_RE.findall(narration):
        parsed = _parse_eval_tag(raw_eval)
        if parsed is None:
            vr.missing_evals.append(raw_eval.strip())
            continue
        kind, value = parsed
        if kind == "mate":
            if not any(
                gk == "mate" and gv == value
                for gk, gv in ground_scores
            ):
                vr.missing_evals.append(raw_eval.strip())
        else:
            # cp: check within tolerance
            if not any(
                gk == "cp" and abs(gv - value) <= EVAL_TOLERANCE_CP
                for gk, gv in ground_scores
            ):
                vr.missing_evals.append(raw_eval.strip())

    # --- grounding citation validation (BBF-87.1) ---
    # Only run if a grounding match was provided. Otherwise the
    # LLM had no grounding block in the prompt, so we don't
    # fault it for not producing <grounding> tags.
    if grounding_match is not None:
        corpus_explanation = grounding_match.narrative_explanation
        for raw_grounding in _GROUNDING_RE.findall(narration):
            citation = raw_grounding.strip()
            if not _grounding_similarity_ok(citation, corpus_explanation):
                # Surface a short preview so the retry / log
                # message is actionable.
                preview = citation[:50] + ("..." if len(citation) > 50 else "")
                vr.grounding_failures.append(
                    f"<grounding>{preview}</grounding>"
                )

    vr.valid = (
        len(vr.missing_moves) == 0
        and len(vr.missing_evals) == 0
        and len(vr.bad_notation) == 0
        and len(vr.grounding_failures) == 0
    )
    return vr


__all__ = [
    "EVAL_TOLERANCE_CP",
    "GROUNDING_MIN_LCS_WORDS",
    "GROUNDING_MIN_OVERLAP_RATIO",
    "ValidationResult",
    "_normalize_move",
    "_parse_eval_tag",
    "_word_tokens",
    "_lcs_word_count",
    "_grounding_similarity_ok",
    "validate_citations",
]
