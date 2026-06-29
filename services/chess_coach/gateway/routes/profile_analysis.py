"""Psychological profiling endpoint.
POST /v1/profile/{player}/analysis
"""
from __future__ import annotations
import logging
import aiosqlite
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from ..auth import require_bearer
from ..route_guard import route_guard

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/profile", tags=["profile"])


def _db_path(request: Request) -> str:
    return str(request.app.state.gateway.settings.sqlite_path)


class ProfileAnalysisResponse(BaseModel):
    player_name: str
    total_games: int
    tactical_tendency: float
    risk_appetite: float
    tilt_index: float
    time_pressure_blunders: float
    opening_breadth: int


@router.post(
    "/{player}/analysis",
    response_model=ProfileAnalysisResponse,
    dependencies=[Depends(require_bearer)],
)
@route_guard
async def get_profile_analysis(
    player: str,
    db_path: str = Depends(_db_path),
) -> ProfileAnalysisResponse:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Resolve default player
        if player == "default":
            row = await db.execute_fetchall(
                """SELECT white AS player, COUNT(*) as cnt FROM games
                   WHERE white != '?' GROUP BY white
                   UNION ALL
                   SELECT black AS player, COUNT(*) as cnt FROM games
                   WHERE black != '?' GROUP BY black
                   ORDER BY cnt DESC LIMIT 1"""
            )
            resolved = row[0]["player"] if row else "unknown"
        else:
            resolved = player

        # Total games
        total_row = await db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM games WHERE white=? OR black=?",
            (resolved, resolved),
        )
        total_games = total_row[0]["cnt"] if total_row else 0

        # --- Tactical tendency + risk appetite + time pressure ---
        # Join: analyses -> positions -> games
        # Side-aware delta: even ply = White moved, odd ply = Black moved
        metrics_rows = await db.execute_fetchall(
            """WITH scored AS (
              SELECT
                an.score_cp,
                po.ply,
                po.game_id,
                LAG(an.score_cp) OVER (PARTITION BY po.game_id ORDER BY po.ply) AS prev_cp
              FROM analyses an
              JOIN positions po ON an.position_id = po.id
              JOIN games g ON po.game_id = g.id
              WHERE (g.white = ? OR g.black = ?)
                AND an.score_cp IS NOT NULL
                AND po.is_mainline = 1
            ),
            deltas AS (
              SELECT
                ply,
                CASE WHEN ply % 2 = 0
                  THEN score_cp - prev_cp
                  ELSE prev_cp - score_cp
                END AS side_delta
              FROM scored
              WHERE prev_cp IS NOT NULL
            )
            SELECT
              COUNT(CASE WHEN ABS(side_delta) > 80 THEN 1 END) AS opportunities,
              COUNT(CASE WHEN ABS(side_delta) > 80 AND side_delta > 0 THEN 1 END) AS taken,
              AVG(CASE WHEN side_delta < 0 AND side_delta > -100 THEN ABS(side_delta) END) AS avg_loss,
              AVG(CASE WHEN ply > 30 AND side_delta < -100 THEN 1.0 ELSE 0.0 END) AS deep_blunder,
              AVG(CASE WHEN ply <= 30 AND side_delta < -100 THEN 1.0 ELSE 0.0 END) AS early_blunder
            FROM deltas""",
            (resolved, resolved),
        )

        if metrics_rows:
            m = metrics_rows[0]
            opps = m["opportunities"] or 0
            taken = m["taken"] or 0
            tactical_tendency = round(taken / opps, 4) if opps > 0 else 0.0
            risk_appetite = round(float(m["avg_loss"] or 0), 2)
            deep = float(m["deep_blunder"] or 0)
            early = float(m["early_blunder"] or 0)
            time_pressure_blunders = round(deep - early, 4)
        else:
            tactical_tendency = risk_appetite = time_pressure_blunders = 0.0

        # --- Tilt index ---
        games_rows = await db.execute_fetchall(
            "SELECT result, white, black FROM games WHERE (white=? OR black=?) ORDER BY rowid ASC",
            (resolved, resolved),
        )
        results = []
        for g in games_rows:
            if g["white"] == resolved:
                results.append("W" if g["result"] == "1-0" else "L" if g["result"] == "0-1" else "D")
            else:
                results.append("W" if g["result"] == "0-1" else "L" if g["result"] == "1-0" else "D")
        baseline = results.count("W") / len(results) if results else 0
        post_loss = [results[i] for i in range(1, len(results)) if results[i-1] == "L"]
        post_loss_rate = post_loss.count("W") / len(post_loss) if post_loss else baseline
        tilt_index = round(max(0.0, baseline - post_loss_rate), 4)

        # --- Opening breadth ---
        breadth_rows = await db.execute_fetchall(
            """SELECT COUNT(DISTINCT SUBSTR(po.move_san, 1, 10)) as breadth
               FROM positions po JOIN games g ON po.game_id = g.id
               WHERE (g.white=? OR g.black=?) AND po.ply <= 10 AND po.move_san IS NOT NULL""",
            (resolved, resolved),
        )
        opening_breadth = breadth_rows[0]["breadth"] if breadth_rows else 0

    return ProfileAnalysisResponse(
        player_name=resolved,
        total_games=total_games,
        tactical_tendency=tactical_tendency,
        risk_appetite=risk_appetite,
        tilt_index=tilt_index,
        time_pressure_blunders=time_pressure_blunders,
        opening_breadth=opening_breadth,
    )
