"""Phase 5 (BBF-64) engine eval-delta verifier.

For each position in a given L-2 corpus version, runs the engine and
compares the engine top-N PVs against the gold labels, producing a
per-position accuracy report + aggregate summary.

This is the calibration baseline for Phase 6 model work and the
regression test for engine eval drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from chess_coach.datasets.l2_gold import L2GoldEntry, load_l2_gold
from chess_coach.engine_orch.pool import EnginePool, EngineSpec
from chess_coach.protocol_types.analysis import AnalysisRequest, AnalysisResult
from chess_coach.protocol_types.analysis import PVLine, Score

router = APIRouter()


class CorpusVersion(str, Enum):
    """L-2 corpus versions supported by the verifier."""

    V1 = "v1"
    V2 = "v2"


@dataclass
class PositionReport:
    """Per-position accuracy result."""

    id: str
    fen: str
    gold_move_uci: str
    gold_score_cp: int
    engine_top_move_uci: str
    engine_top_score_cp: int
    delta_cp: int  # engine.top - gold (signed)
    status: str  # "match_top1" | "match_topN" | "miss"


@dataclass
class VerifySummary:
    """Aggregate stats across the corpus."""

    total: int
    top1_hits: int
    top3_hits: int
    score_within_50cp: int
    mean_delta_cp_abs: float
    max_delta_cp_abs: int


@dataclass
class VerifyResponse:
    """Top-level verifier response shape."""

    corpus_version: CorpusVersion
    summary: VerifySummary
    positions: list[PositionReport] = field(default_factory=list)


async def verify_corpus(
    version: CorpusVersion,
    pool: EnginePool | None = None,
    depth: int = 15,
    top_n: int = 3,
) -> list[PositionReport]:
    """Run the engine against each gold position in version and report per-position accuracy.

    Uses the existing EnginePool (or a fresh one with hash_mb=32).
    Returns a list of PositionReport objects; the route handler aggregates
    into a VerifyResponse.

    Skeleton: this returns [] until the engine-loop lands in Task 2.
    """
    # Skeleton placeholder; Task 2 implements the engine loop.
    return []


@router.get("/v1/eval/verify/{version}", response_model=None)
async def verify_endpoint(
    version: CorpusVersion,
    request: Request,
    depth: int = Query(default=15, ge=8, le=22),
    top_n: int = Query(default=3, ge=1, le=10),
) -> dict[str, Any]:
    """Run the engine against each gold position and return a VerifyResponse.

    Skeleton: returns a 501 stub for now until Task 2 wires up the loop.
    """
    raise HTTPException(
        status_code=501,
        detail=f"eval-delta verifier: scaffolding only (BBF-64 Task 1); verification for {version.value} lands in Task 2",
    )
