"""FEN position embedder for memory_kb pipeline.

Current implementation: sentence-transformers all-MiniLM-L6-v2 (384-dim).
Produces semantically meaningful position clusters across opening/middlegame/endgame.

Replaced TF-IDF (256-dim) on 2026-06-22. Quality gate: e4 vs d4 cosine < 0.85;
opening-to-opening similarity > opening-to-endgame similarity.
See validate_embedder() for the acceptance test.
"""
from __future__ import annotations

import logging

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_FILES = "abcdefgh"
_PIECE_NAMES = {
    "p": "pawn", "n": "knight", "b": "bishop",
    "r": "rook", "q": "queen", "k": "king",
}
_CENTER_SQUARES = {"d4", "e4", "d5", "e5", "c4", "c5", "f4", "f5"}

_model: SentenceTransformer | None = None

# Acceptance-test fixtures — 6 FENs covering distinct game phases and openings.
_FIXTURES = {
    "e4_opening":   "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
    "d4_opening":   "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq d3 0 1",
    "sicilian":     "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 2",
    "middlegame":   "r1bq1rk1/pp2bppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R1BQR1K1 w - - 4 10",
    "rook_ending":  "8/8/4k3/8/4K3/8/4R3/8 w - - 0 1",
    "kq_vs_k":      "8/8/3k4/8/8/8/8/3KQ3 w - - 0 1",
}


def _fen_to_text(fen: str) -> str:
    """Convert FEN to natural-language description for sentence-transformer input."""
    parts = fen.split()
    board = parts[0]
    side = parts[1] if len(parts) > 1 else "w"
    castling = parts[2] if len(parts) > 2 else "-"
    ep = parts[3] if len(parts) > 3 else "-"

    pieces: list[str] = []
    white_material = 0
    black_material = 0
    piece_values = {"p": 1, "n": 3, "b": 3, "r": 5, "q": 9, "k": 0}

    for r_idx, rank in enumerate(board.split("/")):
        f_idx = 0
        for ch in rank:
            if ch.isdigit():
                f_idx += int(ch)
            else:
                sq = _FILES[f_idx] + str(8 - r_idx)
                color = "white" if ch.isupper() else "black"
                name = _PIECE_NAMES[ch.lower()]
                weight = 2 if sq in _CENTER_SQUARES else 1
                for _ in range(weight):
                    pieces.append(f"{color} {name} on {sq}")
                val = piece_values.get(ch.lower(), 0)
                if ch.isupper():
                    white_material += val
                else:
                    black_material += val
                f_idx += 1

    non_pawns = [p for p in pieces if "pawn" not in p]
    phase = (
        "opening" if len(non_pawns) > 12
        else "endgame" if len(non_pawns) < 6
        else "middlegame"
    )
    side_str = "white to move" if side == "w" else "black to move"
    mat_str = f"material white {white_material} black {black_material}"
    castle_str = f"castling {castling}" if castling != "-" else "no castling rights"
    ep_str = f"en passant {ep}" if ep != "-" else ""
    parts_out = [phase, side_str, mat_str, castle_str]
    if ep_str:
        parts_out.append(ep_str)
    parts_out.extend(pieces[:20])  # cap to avoid token overflow
    return " ".join(parts_out)


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("embedder: loading all-MiniLM-L6-v2")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("embedder: model loaded")
    return _model


def fit_and_embed(fens: list[str]) -> np.ndarray:
    """Embed a corpus of FENs. Returns float32 array shape (n, 384).

    'fit_and_embed' name retained for API compatibility with pipeline.py.
    No fitting step is needed for sentence-transformers — the model is
    pretrained. This function simply encodes the full corpus.
    """
    model = _get_model()
    texts = [_fen_to_text(f) for f in fens]
    return model.encode(texts, convert_to_numpy=True).astype(np.float32)


def embed(fens: list[str]) -> np.ndarray:
    """Embed a list of FENs. Returns float32 array shape (n, 384)."""
    return fit_and_embed(fens)


def embed_one(fen: str) -> np.ndarray:
    """Embed a single FEN. Returns float32 array shape (384,).

    Raises RuntimeError if the model cannot be loaded.
    """
    try:
        return embed([fen])[0]
    except Exception as exc:
        raise RuntimeError(f"embedder: failed to embed FEN: {exc}") from exc


def validate_embedder() -> bool:
    """Run acceptance test against _FIXTURES. Returns True if quality gate passes.

    Gate: e4_opening vs d4_opening cosine < 0.85
          opening-to-opening similarity > opening-to-endgame similarity

    Logs results at INFO level. Called from gateway health check.
    """
    from sklearn.metrics.pairwise import cosine_similarity  # local import, optional dep

    vecs = {k: embed_one(v) for k, v in _FIXTURES.items()}

    def cos(a: str, b: str) -> float:
        return float(cosine_similarity([vecs[a]], [vecs[b]])[0][0])

    e4_d4 = cos("e4_opening", "d4_opening")
    open_open = cos("e4_opening", "sicilian")
    open_end = cos("e4_opening", "rook_ending")

    gate1 = e4_d4 < 0.85
    gate2 = open_open > open_end

    logger.info(
        "embedder validate: e4_d4=%.3f (<0.85=%s) open_open=%.3f open_end=%.3f (open>end=%s)",
        e4_d4, gate1, open_open, open_end, gate2,
    )
    passed = gate1 and gate2
    if not passed:
        logger.warning("embedder validate: FAILED quality gate")
    return passed
