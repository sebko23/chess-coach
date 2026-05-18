"""Citation extraction and ground-truth validation."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from chess_coach.protocol_types.analysis import AnalysisResult, Score

try:
    import chess
except ImportError:
    chess = None  # type: ignore[assignment]

_MOVE_RE = re.compile(r"<move>([^<]+)</move>")
_EVAL_RE = re.compile(r"<eval>([^<]+)</eval>")
EVAL_TOLERANCE_CP = 20  # ±0.20 pawns


@dataclass
class ValidationResult:
    """Result of citation validation."""
    valid: bool = True
    missing_moves: list[str] = field(default_factory=list)
    missing_evals: list[str] = field(default_factory=list)
    bad_notation: list[tuple[str, str]] = field(default_factory=list)


def _normalize_move(fen: str, san: str) -> str | None:
    if chess is None:
        return san
    try:
        board = chess.Board(fen)
        move = board.parse_san(san)
        return move.uci()
    except Exception:
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


def validate_citations(
    narration: str,
    result: AnalysisResult,
) -> ValidationResult:
    vr = ValidationResult()
    ground_moves = _collect_ground_truth_moves(result)
    ground_scores = [_score_to_tuple(pv.score) for pv in result.pvs]
    any_mate_gt = any(k == "mate" for k, _ in ground_scores)

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
        raw_eval = raw_eval.strip()
        if raw_eval.startswith("#") or raw_eval.startswith("mate"):
            if not any_mate_gt:
                vr.missing_evals.append(raw_eval)
            continue
        try:
            cp_claimed = round(float(raw_eval) * 100)
        except ValueError:
            vr.missing_evals.append(raw_eval)
            continue
        if not any(
            k == "cp" and abs(v - cp_claimed) <= EVAL_TOLERANCE_CP
            for k, v in ground_scores
        ):
            vr.missing_evals.append(raw_eval)

    vr.valid = (
        len(vr.missing_moves) == 0
        and len(vr.missing_evals) == 0
        and len(vr.bad_notation) == 0
    )
    return vr
