"""FEN position embedder for memory_kb pipeline.

Current implementation: TF-IDF on center-weighted piece-square text.
Provides coarse clustering by game phase and material balance.
Correctly distinguishes endgame vs middlegame vs opening phases.

# TODO: replace _fen_to_text() with coordinate-aware token format (e.g. P_e4, N_f3)
# and swap TF-IDF for sentence-transformers 'all-MiniLM-L6-v2' once token format
# reduces e4 vs d4 cosine similarity below 0.90. See scripts/qdrant_spike.py.
"""
from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

_FILES = "abcdefgh"
_PIECE_NAMES = {
    "p": "pawn", "n": "knight", "b": "bishop",
    "r": "rook", "q": "queen", "k": "king",
}
_CENTER_SQUARES = {"d4", "e4", "d5", "e5", "c4", "c5", "f4", "f5"}

_vectorizer: TfidfVectorizer | None = None


def _fen_to_text(fen: str) -> str:
    """Convert FEN to center-weighted piece-square text description."""
    parts = fen.split()
    board, side = parts[0], parts[1] if len(parts) > 1 else "w"
    pieces: list[str] = []
    for r_idx, rank in enumerate(board.split("/")):
        f_idx = 0
        for ch in rank:
            if ch.isdigit():
                f_idx += int(ch)
            else:
                sq = _FILES[f_idx] + str(8 - r_idx)
                color = "white" if ch.isupper() else "black"
                name = _PIECE_NAMES[ch.lower()]
                pieces.append(f"{color}-{name}-{sq}")
                f_idx += 1

    center = [p for p in pieces if p.split("-")[2] in _CENTER_SQUARES]
    other = [p for p in pieces if p not in center]
    non_pawns = [p for p in pieces if "pawn" not in p]
    phase = (
        "opening" if len(non_pawns) > 12
        else "endgame" if len(non_pawns) < 6
        else "middlegame"
    )
    side_str = "white-to-move" if side == "w" else "black-to-move"
    return f"{phase} {side_str} CENTER: {' '.join(center)} REST: {' '.join(other[:12])}"


def fit_and_embed(fens: list[str]) -> np.ndarray:
    """Fit TF-IDF vocabulary on corpus and return dense vectors.

    Call this once when indexing the full position corpus.
    The fitted vectorizer is cached in module state for subsequent embed() calls.
    """
    global _vectorizer
    texts = [_fen_to_text(f) for f in fens]
    _vectorizer = TfidfVectorizer(max_features=256)
    matrix = _vectorizer.fit_transform(texts)
    return matrix.toarray().astype(np.float32)


def embed(fens: list[str]) -> np.ndarray:
    """Embed FENs using the fitted TF-IDF vectorizer.

    Requires fit_and_embed() to have been called first.
    Raises RuntimeError if vectorizer is not fitted.
    """
    if _vectorizer is None:
        raise RuntimeError(
            "Vectorizer not fitted. Call fit_and_embed() before embed()."
        )
    texts = [_fen_to_text(f) for f in fens]
    matrix = _vectorizer.transform(texts)
    return matrix.toarray().astype(np.float32)


def embed_one(fen: str) -> np.ndarray:
    """Convenience wrapper for single-FEN embedding."""
    return embed([fen])[0]
