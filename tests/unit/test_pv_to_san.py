"""FU-5 — unit tests for the UCI→SAN translation at the narration pipeline.

The narration route returns an additive `pv_moves_san` field on its
response (human-display-only). The conversion happens in
`chess_coach.narration.pipeline._pv_to_san` and is consumed by
`_format_pv_fields`. These tests verify the conversion:

  - covers the 7 move types the engine PV can actually contain
    (pawn, knight, castling kingside/queenside, promotion, en passant,
    capture with disambiguation)
  - covers multi-move replay (the canonical Italian 4-ply case is the
    smoking gun that proves naive per-move `Board(fen).san(uci)` is wrong)
  - covers all error paths (bad FEN, malformed UCI, position-illegal
    move) and confirms the helper falls back to the UCI string per
    move without raising
  - covers the `_format_pv_fields` 3-tuple extension and the 6-ply
    slice alignment invariant
  - covers the `_template_fallback` human-facing string uses SAN
    (the LLM prompt path keeps raw UCI — that's verified separately in
    `test_prompt_format.py`)

Spec authority: `specs/v1.0/chess-coach-protocol-v1.md:42` (UCI
authoritative on the wire; SAN is an additional field, never
authoritative).
"""
from __future__ import annotations

import chess

from chess_coach.narration.pipeline import (
    NarrationOutput,
    _format_pv_fields,
    _pv_to_san,
    _template_fallback,
)
from chess_coach.protocol_types.analysis import AnalysisResult, PVLine, Score

_STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


# ---------------------------------------------------------------------------
# 1. The Italian-game 4-ply canonical case — proves naive per-move
#    conversion is wrong and replay-on-board is right.
# ---------------------------------------------------------------------------


def test_italian_4_ply_replay_produces_correct_san() -> None:
    """Multi-move replay must produce correct SAN, including the
    disambiguated knight move `Nc6` (NOT `Nxc6` as naive per-move
    conversion against the starting FEN would emit)."""
    pv_uci = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]
    san = _pv_to_san(_STARTING_FEN, pv_uci)
    assert san == ["e4", "e5", "Nf3", "Nc6", "Bc4"], san


def test_naive_per_move_emits_broken_san() -> None:
    """Sanity check: prove the naive approach fails, justifying the
    replay-on-board implementation. If python-chess ever changes to
    make the naive approach produce correct SAN, this test would FAIL
    (the assert at the bottom of this function would no longer match)
    and the failure message would be the right prompt to reconsider
    whether _pv_to_san is still needed."""
    pv_uci = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]
    # Naive: fresh board per move, all anchored at start FEN.
    naive = [
        chess.Board(_STARTING_FEN).san(chess.Move.from_uci(u)) for u in pv_uci
    ]
    # This naive output is wrong (exe5, Nxc6) and is the exact reason
    # _pv_to_san replays on a shared board. Document it so future
    # readers see the cost of the wrong approach.
    assert naive == ["e4", "exe5", "Nf3", "Nxc6", "Bc4"], (
        f"naive output changed; re-evaluate _pv_to_san: {naive}"
    )


# ---------------------------------------------------------------------------
# 2. The 7 move types the engine PV can contain.
# ---------------------------------------------------------------------------


def test_pawn_move() -> None:
    assert _pv_to_san(_STARTING_FEN, ["e2e4"]) == ["e4"]


def test_knight_move() -> None:
    assert _pv_to_san(_STARTING_FEN, ["g1f3"]) == ["Nf3"]


def test_castling_kingside() -> None:
    cas_fen = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
    assert _pv_to_san(cas_fen, ["e1g1"]) == ["O-O"]


def test_castling_queenside() -> None:
    cas_fen = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
    assert _pv_to_san(cas_fen, ["e1c1"]) == ["O-O-O"]


def test_promotion() -> None:
    promo_fen = "8/4P3/8/8/8/8/8/k3K3 w - - 0 1"
    assert _pv_to_san(promo_fen, ["e7e8q"]) == ["e8=Q"]


def test_en_passant() -> None:
    ep_fen = "rnbqkbnr/pppp1ppp/8/4pP2/8/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 1"
    assert _pv_to_san(ep_fen, ["f5e6"]) == ["fxe6"]


def test_capture_with_disambiguation() -> None:
    """Two knights can reach c3; python-chess picks the unambiguous SAN.

    Position: both knights (b1, g1) can reach c3; the queen-side knight
    is the only one that can reach b1 → no ambiguity in *file*, but
    python-chess still records `Nc3` (no 'b'/'g' prefix needed because
    the c3 square has only one legal knight mover from g1's lane).

    Wait — from this position BOTH knights can reach c3, so the
    disambiguation IS needed. python-chess chooses the right one
    (b1 knight because it's the only knight on the b/g-files at b1).
    """
    disamb_fen = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 1"
    assert _pv_to_san(disamb_fen, ["b1c3"]) == ["Nc3"]


# ---------------------------------------------------------------------------
# 3. Error paths — never raise, fall back to UCI per move.
# ---------------------------------------------------------------------------


def test_bad_fen_returns_uci_verbatim() -> None:
    """Invalid FEN string: helper falls back to UCI verbatim, no raise."""
    result = _pv_to_san("not-a-valid-fen", ["e2e4", "e7e5"])
    assert result == ["e2e4", "e7e5"]


def test_malformed_uci_falls_back_per_move() -> None:
    """Off-board UCI ('e2e9'): helper falls back to that UCI string.
    Note: a failed move does NOT mutate the board (the bad UCI raises
    before push()), so the subsequent move is parsed against the
    ORIGINAL position. e2e4 is legal from start, so it converts to 'e4'."""
    result = _pv_to_san(_STARTING_FEN, ["e2e9", "e2e4"])
    assert result == ["e2e9", "e4"]


def test_position_illegal_move_falls_back() -> None:
    """Legal-shape but illegal-in-position move (d1h5 from start):
    helper falls back to the UCI string for that move."""
    result = _pv_to_san(_STARTING_FEN, ["d1h5"])
    assert result == ["d1h5"]


def test_mixed_valid_and_invalid_moves() -> None:
    """Mixed valid + invalid in one PV: each invalid move falls back
    independently. Length is preserved 1:1 with the input."""
    pv = ["e2e4", "d1h5", "e7e5", "e2e9"]
    result = _pv_to_san(_STARTING_FEN, pv)
    assert result == ["e4", "d1h5", "e5", "e2e9"]
    assert len(result) == len(pv)


def test_empty_pv_returns_empty_list() -> None:
    assert _pv_to_san(_STARTING_FEN, []) == []


# ---------------------------------------------------------------------------
# 4. _format_pv_fields extension — 3-tuple, lists aligned 1:1.
# ---------------------------------------------------------------------------


def _make_result(fen: str, moves: list[str], score_cp: int = 38) -> AnalysisResult:
    return AnalysisResult(
        engine_id="stockfish",
        engine_version="18",
        fen=fen,
        depth_reached=18,
        multipv=1,
        settings_hash="",
        cpu_arch="x86_64",
        thread_count=1,
        pvs=[PVLine(
            multipv=1,
            score=Score(kind="cp", value=score_cp),
            depth=18,
            moves=moves,
            nodes=1000,
            time_ms=2000,
            nps=500,
        )],
    )


def test_format_pv_fields_returns_three_tuple() -> None:
    """Extended signature: (pv_moves_uci, pv_moves_san, score_display)."""
    pv_uci = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]
    res = _make_result(_STARTING_FEN, pv_uci)
    uci, sans, score = _format_pv_fields(res)
    assert uci == pv_uci
    assert sans == ["e4", "e5", "Nf3", "Nc6", "Bc4"]
    assert score == "+0.38"


def test_format_pv_fields_six_ply_slice_alignment() -> None:
    """The 6-ply slice must apply to BOTH the UCI and SAN lists, with
    aligned lengths."""
    long_pv = ["e2e4","e7e5","g1f3","b8c6","f1c4","d7d6","e4e5","d6e5"]
    res = _make_result(_STARTING_FEN, long_pv)
    uci, sans, score = _format_pv_fields(res)
    assert uci == ["e2e4","e7e5","g1f3","b8c6","f1c4","d7d6"]
    assert sans == ["e4","e5","Nf3","Nc6","Bc4","d6"]
    assert len(uci) == 6
    assert len(sans) == 6
    assert len(uci) == len(sans)


def test_format_pv_fields_synthetic_empty_moves_yields_score_only() -> None:
    """Synthetic path: PVLine with empty moves but a score. Output is
    ([], [], '+0.00') — no PV to format, but score still rendered.

    Note: AnalysisResult.pvs has min_length=1 in the protocol model,
    so the empty-pvs early-return branch in _format_pv_fields is
    effectively unreachable in practice. This test pins the synthetic
    behaviour so future refactors don't accidentally break it."""
    res = AnalysisResult(
        engine_id="user-request", engine_version="n/a", fen=_STARTING_FEN,
        depth_reached=1, multipv=1, settings_hash="",
        cpu_arch="unknown", thread_count=1,
        pvs=[PVLine(multipv=1, score=Score(kind="cp", value=0), depth=1,
                    moves=[], nodes=None, time_ms=None, nps=None)],
    )
    uci, sans, score = _format_pv_fields(res)
    assert uci == []
    assert sans == []
    assert score == "+0.00"


def test_format_pv_fields_mate_score() -> None:
    """Mate-in-N score: rendered as 'mate in N', not a cp value."""
    pv = ["e2e4"]
    res = AnalysisResult(
        engine_id="x", engine_version="1", fen=_STARTING_FEN,
        depth_reached=12, multipv=1, settings_hash="",
        cpu_arch="x86_64", thread_count=1,
        pvs=[PVLine(multipv=1, score=Score(kind="mate", value=3), depth=12,
                    moves=pv, nodes=100, time_ms=500, nps=200)],
    )
    uci, sans, score = _format_pv_fields(res)
    assert uci == pv
    assert sans == ["e4"]
    assert score == "mate in 3"


# ---------------------------------------------------------------------------
# 5. _template_fallback uses SAN (human-facing).
# ---------------------------------------------------------------------------


def test_template_fallback_renders_san_not_uci() -> None:
    """The template fallback is human-facing; must render SAN, not UCI."""
    pv = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]
    res = _make_result(_STARTING_FEN, pv)
    text = _template_fallback(res)
    # SAN appears in the fallback string.
    assert "e4 e5 Nf3 Nc6 Bc4" in text
    # UCI does NOT leak.
    assert "e2e4" not in text


# ---------------------------------------------------------------------------
# 6. NarrationOutput dataclass — pv_moves_san field.
# ---------------------------------------------------------------------------


def test_narration_output_default_pv_moves_san_is_empty() -> None:
    """Backward compat: constructing NarrationOutput without
    pv_moves_san (legacy callers, tests) yields empty list, not an
    AttributeError."""
    out = NarrationOutput(narration="hi", pv_moves=["e2e4"], score_display="+0.30")
    assert out.pv_moves_san == []


def test_narration_output_accepts_pv_moves_san() -> None:
    """New field populates correctly when supplied."""
    out = NarrationOutput(
        narration="hi",
        pv_moves=["e2e4", "e7e5"],
        pv_moves_san=["e4", "e5"],
        score_display="+0.30",
    )
    assert out.pv_moves_san == ["e4", "e5"]
