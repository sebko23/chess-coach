"""Pydantic models for the narration route (POST /v1/narration/explain)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

try:
    import chess
except ImportError:
    chess = None  # type: ignore[assignment]


class NarrationRequest(BaseModel):
    """Body of POST /v1/narration/explain."""

    fen: str = Field(
        ...,
        description="FEN position to analyse and narrate",
        examples=["rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"],
    )
    depth: int = Field(default=12, ge=6, le=30, description="Engine search depth")
    engine_id: str = Field(default="stockfish", description="Engine id to use")
    multipv: int = Field(default=1, ge=1, le=5, description="Number of PVs")

    @field_validator("fen")
    @classmethod
    def validate_fen(cls, v: str) -> str:
        """Reject malformed FEN before it reaches the engine."""
        if chess is None:
            return v  # can't validate without python-chess
        try:
            chess.Board(v)
        except ValueError as e:
            raise ValueError(f"Invalid FEN: {e}") from e
        return v


class NarrationResponse(BaseModel):
    """Response from POST /v1/narration/explain.

    Contains the validated narration text and a compact analysis summary
    (not the raw AnalysisResult dump — the frontend gets what it needs).
    """

    fen: str = Field(..., description="Position that was analysed")
    narration: str = Field(..., description="Grounded coaching narration")
    depth_reached: int = Field(..., description="Max engine depth reached")
    best_move: str = Field(..., description="Best move in SAN notation")
    score_display: str = Field(..., description="Human-readable score, e.g. '+0.38' or 'mate in 2'")
    pv_moves: list[str] = Field(..., description="Top PV line moves in SAN")
