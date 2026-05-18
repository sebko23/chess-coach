"""Pydantic models for engine analysis.

Matches protocol §6 (engine analysis canonical form) and the
engine routes declared in protocol §4.6.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from .envelopes import _ProtocolModel


class Score(_ProtocolModel):
    """Evaluation score — either centipawns or mate-in-N."""

    kind: Literal["cp", "mate"] = Field(..., description="`cp` | `mate`")
    value: int = Field(
        ...,
        description="Centipawn value (always from White's POV), or mate distance in plies",
    )


class PVLine(_ProtocolModel):
    """One principal variation."""

    multipv: int = Field(..., ge=1, description="MultiPV index (1-indexed)")
    score: Score = Field(..., description="Evaluation from the engine's perspective")
    depth: int = Field(..., ge=1, description="Depth at which this PV was calculated")
    moves: list[str] = Field(..., description="UCI moves, e.g. ['e2e4', 'e7e5']")
    nodes: int | None = Field(default=None, ge=0, description="Nodes searched")
    time_ms: int | None = Field(default=None, ge=0, description="Search time in milliseconds")
    nps: int | None = Field(default=None, ge=0, description="Nodes per second")


class AnalysisResult(_ProtocolModel):
    """Canonical analysis result (protocol §6).

    This is the final event emitted on ``engine.<job_id>`` when the analysis
    is complete, and the shape stored in ``engine_analyses`` for caching.
    """

    engine_id: str = Field(..., description="Human-readable engine identifier, e.g. 'sf18'")
    engine_version: str = Field(..., description="Engine version string")
    fen: str = Field(..., description="FEN position that was analysed")
    depth_reached: int = Field(..., ge=1, description="Maximum depth reached")
    multipv: int = Field(..., ge=1, description="Number of PVs requested")
    settings_hash: str = Field(..., description="Hash of UCI options used")
    cpu_arch: str = Field(..., description="CPU architecture string, e.g. 'x86_64-avx2'")
    thread_count: int = Field(..., ge=1, description="Number of search threads used")
    pvs: list[PVLine] = Field(..., min_length=1, description="Ordered best-to-worst")


class EngineCapability(_ProtocolModel):
    """One UCI option exposed by an engine."""

    name: str = Field(..., description="UCI option name, e.g. 'Hash'")
    type: Literal["spin", "check", "combo", "button", "string"]
    default: str | int = Field(..., description="Default value")
    min: int | None = Field(default=None, description="Minimum (spin only)")
    max: int | None = Field(default=None, description="Maximum (spin only)")
    vars: list[str] | None = Field(default=None, description="Allowed values (combo only)")


class EngineInfo(_ProtocolModel):
    """Returned by ``GET /engines/{engine_id}``."""

    engine_id: str
    name: str = Field(..., description="Full engine name")
    version: str = Field(..., description="Version string from the binary")
    path: str = Field(..., description="Absolute path on the Backend host")
    state: Literal["ready", "busy", "unavailable"]
    capabilities: list[EngineCapability] = Field(default_factory=list)
    memory_mode: Literal["standard", "lite", "full"] = "standard"


class AnalysisRequest(_ProtocolModel):
    """Body of ``POST /engines/{engine_id}/analyze``."""

    fen: str = Field(
        ...,
        description="FEN position to analyze",
        examples=["rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"],
    )
    depth: int | None = Field(default=None, ge=1, description="Search depth (plies)")
    nodes: int | None = Field(default=None, ge=1, description="Search node limit")
    multipv: int = Field(default=1, ge=1, le=5, description="Number of PVs to return")
    engine_id: str | None = Field(default=None, description="Engine to use (optional shortcut; normally from URL path)")
    options: dict[str, str | int | bool] = Field(
        default_factory=dict, description="Extra UCI options within engine bounds"
    )
    stream: bool = Field(default=False, description="If true, open engine.<job_id> WS topic")
