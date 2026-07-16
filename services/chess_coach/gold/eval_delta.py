"""Multi-PV eval-delta generator wrapping the engine orchestrator.

Per BBF-63: takes a FEN, runs an analysis with multi-PV=top_n, and returns
a list of {move_uci, score_cp, delta_cp} dicts - one per PV, with delta_cp
computed as score_cp - score_cp_of_best_line.

The module exposes eval_deltas(fen, depth=15, top_n=3, pool=None).
When pool=None, a fresh EnginePool is created with a default stockfish spec.
Tests inject a fake pool to avoid spawning real subprocesses.
"""
from __future__ import annotations

import os

from chess_coach.engine_orch.pool import EnginePool, EngineSpec
from chess_coach.protocol_types.analysis import AnalysisRequest, AnalysisResult


def _default_pool() -> EnginePool:
    """Best-effort default pool. Will fail loudly if stockfish is unavailable."""
    path = os.environ.get("CHESS_COACH_STOCKFISH_PATH", "/usr/games/stockfish")
    return EnginePool(
        specs=[EngineSpec(engine_id="stockfish", path=path)],
        max_workers=1,
        default_depth=22,
    )


async def eval_deltas(
    fen: str,
    depth: int = 15,
    top_n: int = 3,
    pool: EnginePool | None = None,
) -> list[dict]:
    """Run engine analysis at the given depth with multi-PV=top_n.

    Returns a list of {"move_uci": str, "score_cp": int, "delta_cp": int}.
    The first entry is the engine's best line and has delta_cp == 0.
    """
    pool = pool or _default_pool()
    request = AnalysisRequest(fen=fen, depth=depth, multipv=top_n)
    result: AnalysisResult = await pool.analyze(request, engine_id="stockfish")

    if not result.pvs:
        return []

    def score_cp(pv) -> int:
        score = pv.score
        if score.kind == "cp" and score.value is not None:
            return int(score.value)
        return 0

    best_score = score_cp(result.pvs[0])
    deltas: list[dict] = []
    for pv in result.pvs:
        if not pv.moves:
            continue
        value = score_cp(pv)
        deltas.append(
            {
                "move_uci": str(pv.moves[0]),
                "score_cp": value,
                "delta_cp": value - best_score,
            }
        )
        if len(deltas) >= top_n:
            break
    return deltas
