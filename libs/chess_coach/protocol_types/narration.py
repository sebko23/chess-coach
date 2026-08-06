"""Pydantic models for the narration route (POST /v1/narration/explain)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

try:
    import chess
except ImportError:
    chess = None  # type: ignore[assignment]


class NarrationRequest(BaseModel):
    """Body of POST /v1/narration/explain.

    Supports two consumption modes:
      1. Simple narration (no engine call): the route accepts pre-computed
         context (move_san, eval_cp, game_phase, player_name, context) and
         skips engine invocation. depth/engine_id/multipv are ignored.
      2. Engine-backed narration (future Phase 3 endpoint): depth,
         engine_id, multipv drive a real engine analysis before narration.

    All optional fields default to None so the type remains compatible
    with both modes and with clients that only know the simple contract.
    """

    # Required
    fen: str = Field(
        ...,
        description="FEN position to analyse and narrate",
        examples=["rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"],
    )

    # Simple-narration inputs (consumed by the /explain route today)
    move_san: str | None = Field(
        default=None,
        description="Move just played in SAN, if known (e.g. 'Nf6', 'e4').",
    )
    eval_cp: int | None = Field(
        default=None,
        description="Pre-computed evaluation in centipawns (positive = white).",
    )
    game_phase: str | None = Field(
        default=None,
        description='One of "opening", "middlegame", "endgame".',
    )
    player_name: str | None = Field(
        default=None,
        description="Optional player name for personalised narration.",
    )
    context: str | None = Field(
        default=None,
        description="Free-form extra context appended to the narration prompt.",
    )

    # Engine-backed inputs (consumed by a future engine-backed endpoint)
    depth: int | None = Field(
        default=None,
        ge=6,
        le=30,
        description="Engine search depth. None = use endpoint default (12).",
    )
    engine_id: str | None = Field(
        default=None,
        description="Engine id to use. None = use endpoint default ('stockfish').",
    )
    multipv: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Number of PVs. None = use endpoint default (1).",
    )

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
    depth_reached: int | None = Field(
        default=None,
        description=(
            "Max engine depth reached. "
            "Populated only when narration is engine-backed; "
            "None for template/LLM-only paths."
        ),
    )
    best_move: str | None = Field(
        default=None,
        description=(
            "Best move in UCI notation (e.g. 'e2e4'). "
            "Populated only when narration is engine-backed; "
            "None for template/LLM-only paths."
        ),
    )
    score_display: str = Field(..., description="Human-readable score, e.g. '+0.38' or 'mate in 2'")
    pv_moves: list[str] = Field(
        ...,
        description=(
            "Top PV line moves in UCI notation "
            '(e.g. ["e2e4", "e7e5"])'
        ),
    )
    # FU-5: human-display SAN translation of pv_moves. UCI in pv_moves
    # is authoritative on the wire per
    # specs/v1.0/chess-coach-protocol-v1.md:42; pv_moves_san is for
    # display only and is never authoritative. Length is always
    # aligned 1:1 with pv_moves (same plies, same order).
    pv_moves_san: list[str] = Field(
        default_factory=list,
        description=(
            "Top PV line moves in SAN notation "
            '(e.g. ["e4", "e5", "Nf3"]), human-display-only. '
            "Authoritative on the wire is pv_moves (UCI); "
            "SAN here is never authoritative "
            "(specs/v1.0/chess-coach-protocol-v1.md:42). "
            "Length matches pv_moves 1:1."
        ),
    )
    # BBF-87.1: which v2 narrative corpus entry grounded this narration.
    # None when the FEN is not in the corpus (no grounding block
    # injected; pipeline ran without narrative grounding).
    corpus_entry_id: str | None = Field(
        default=None,
        description=(
            "The v2 narrative corpus entry (NG-v2-NNNN) whose "
            "narrative_explanation grounded this narration. "
            "None when no FEN match in the corpus."
        ),
    )
