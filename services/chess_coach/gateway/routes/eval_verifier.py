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


def _miss_report(entry: L2GoldEntry) -> PositionReport:
    """Build a 'miss' PositionReport for engine failures or empty PVs."""
    return PositionReport(
        id=entry.id,
        fen=entry.fen,
        gold_move_uci=entry.best_move_uci,
        gold_score_cp=entry.score_cp,
        engine_top_move_uci="",
        engine_top_score_cp=0,
        delta_cp=99999,
        status="miss",
    )


async def verify_corpus(
    version: CorpusVersion,
    pool: EnginePool | None = None,
    depth: int = 15,
    top_n: int = 3,
) -> list[PositionReport]:
    """Run the engine against each gold position in `version` and report.

    The route handler instantiates the pool with the shared-pool pattern
    (hash_mb=32, single pool across all positions) when pool=None.
    Tests inject a mocked pool.
    """
    if pool is None:
        # Production default: shared pool with hash_mb=32.
        pool = EnginePool(
            specs=[EngineSpec(engine_id="stockfish", path="/usr/games/stockfish")],
            max_workers=1,
            default_depth=depth,
            default_hash_mb=32,
        )

    positions: list[L2GoldEntry] = load_l2_gold(version.value)
    reports: list[PositionReport] = []
    for entry in positions:
        req = AnalysisRequest(fen=entry.fen, depth=depth, multipv=top_n)
        try:
            result = await pool.analyze(req, engine_id="stockfish")
        except Exception:
            # Skip position on engine failure; report as miss with delta=99999.
            reports.append(_miss_report(entry))
            continue

        if not result.pvs:
            reports.append(_miss_report(entry))
            continue

        top = result.pvs[0]
        if not top.moves:
            reports.append(_miss_report(entry))
            continue

        # Convert cp/mate score to int; mate scores use 10000 sentinel.
        if top.score.kind == "cp":
            engine_top_cp = int(top.score.value)
        else:
            engine_top_cp = 10000 if (top.score.value or 0) > 0 else -10000

        delta_cp = engine_top_cp - entry.score_cp

        # Status: match_top1 if exact top-1 match; match_topN if in top-N;
        # miss otherwise.
        engine_moves_top_n = [str(pv.moves[0]) for pv in result.pvs if pv.moves]
        if engine_moves_top_n[0] == entry.best_move_uci:
            status = "match_top1"
        elif entry.best_move_uci in engine_moves_top_n:
            status = "match_topN"
        else:
            status = "miss"

        reports.append(PositionReport(
            id=entry.id,
            fen=entry.fen,
            gold_move_uci=entry.best_move_uci,
            gold_score_cp=entry.score_cp,
            engine_top_move_uci=engine_moves_top_n[0],
            engine_top_score_cp=engine_top_cp,
            delta_cp=delta_cp,
            status=status,
        ))
    return reports


@router.get("/v1/eval/verify/{version}", response_model=None)
async def verify_endpoint(
    version: CorpusVersion,
    request: Request,
    depth: int = Query(default=15, ge=8, le=22),
    top_n: int = Query(default=3, ge=1, le=10),
) -> dict[str, Any]:
    """Run the engine against each gold position; return a VerifyResponse.

    Response shape (dict; not a Pydantic model — dataclass-to-dict pattern is
    faster and the shape is documented here):

        {
            "corpus_version": "v1" | "v2",
            "summary": {
                "total": int,
                "top1_hits": int,
                "top3_hits": int,
                "score_within_50cp": int,
                "mean_delta_cp_abs": float,
                "max_delta_cp_abs": int,
            },
            "positions": [
                {
                    "id": str,
                    "fen": str,
                    "gold_move_uci": str,
                    "gold_score_cp": int,
                    "engine_top_move_uci": str,
                    "engine_top_score_cp": int,
                    "delta_cp": int,
                    "status": "match_top1" | "match_topN" | "miss",
                },
                ...
            ],
        }
    """
    reports = await verify_corpus(version, pool=None, depth=depth, top_n=top_n)

    # Aggregate
    total = len(reports)
    top1_hits = sum(1 for r in reports if r.status == "match_top1")
    top3_hits = sum(1 for r in reports if r.status in {"match_top1", "match_topN"})
    score_within_50cp = sum(
        1 for r in reports
        if r.status != "miss" and abs(r.delta_cp) <= 50
    )
    if total > 0:
        valid_deltas = [abs(r.delta_cp) for r in reports if r.status != "miss"]
        if valid_deltas:
            mean_delta_abs = sum(valid_deltas) / len(valid_deltas)
            max_delta_abs = max(valid_deltas)
        else:
            mean_delta_abs = 0.0
            max_delta_abs = 0
    else:
        mean_delta_abs = 0.0
        max_delta_abs = 0

    return {
        "corpus_version": version.value,
        "summary": {
            "total": total,
            "top1_hits": top1_hits,
            "top3_hits": top3_hits,
            "score_within_50cp": score_within_50cp,
            "mean_delta_cp_abs": mean_delta_abs,
            "max_delta_cp_abs": max_delta_abs,
        },
        "positions": [
            {
                "id": r.id,
                "fen": r.fen,
                "gold_move_uci": r.gold_move_uci,
                "gold_score_cp": r.gold_score_cp,
                "engine_top_move_uci": r.engine_top_move_uci,
                "engine_top_score_cp": r.engine_top_score_cp,
                "delta_cp": r.delta_cp,
                "status": r.status,
            }
            for r in reports
        ],
    }