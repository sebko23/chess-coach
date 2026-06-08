"""Psychological profiling — player tendency analysis (Phase 5 Option A).

Returns metrics derived from 551 games + 24,962 position analyses.
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from chess_coach.gateway.auth import require_bearer

router = APIRouter(tags=["profile"], dependencies=[Depends(require_bearer)])


class ProfileAnalysisResult(BaseModel):
    player_name: str
    total_games: int
    tactical_tendency: float
    risk_appetite: float
    tilt_index: float
    time_pressure_blunders: float
    opening_breadth: int


@router.post("/v1/profile/{player}/analysis", response_model=ProfileAnalysisResult)
async def get_profile_analysis(player: str, request: Request):
    """Compute 5 psychological metrics for a player from game/position/analysis data."""
    settings = request.app.state.gateway.settings
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        db.row_factory = aiosqlite.Row

        # --- 1. Total games for the player ---
        cur = await db.execute(
            "SELECT COUNT(*) FROM games WHERE white = ? OR black = ?",
            (player, player),
        )
        total_games = (await cur.fetchone())[0]

        # --- 2. Tactical tendency ---
        # Find positions where cp_delta > 200 (tactical opportunity)
        # Check if next position's cp_delta < 50 (player recovered = took the tactic)
        cur = await db.execute(
            """
            WITH player_games AS (
                SELECT id FROM games WHERE white = ? OR black = ?
            ),
            tactical_opps AS (
                SELECT
                    a.position_id,
                    p.game_id,
                    p.ply,
                    a.cp_delta
                FROM analyses a
                JOIN positions p ON p.id = a.position_id
                JOIN player_games pg ON pg.id = p.game_id
                WHERE ABS(COALESCE(a.cp_delta, 0)) > 200
                  AND p.is_mainline = 1
            ),
            next_position AS (
                SELECT
                    t.position_id,
                    t.game_id,
                    t.ply,
                    t.cp_delta AS opp_delta,
                    n.cp_delta AS next_delta
                FROM tactical_opps t
                LEFT JOIN positions p2 ON p2.game_id = t.game_id AND p2.ply = t.ply + 1 AND p2.is_mainline = 1
                LEFT JOIN analyses n ON n.position_id = p2.id
            )
            SELECT
                COUNT(*) AS total_opps,
                SUM(CASE WHEN next_delta IS NOT NULL AND ABS(COALESCE(next_delta, 0)) < 50 THEN 1 ELSE 0 END) AS taken
            FROM next_position
            """,
            (player, player),
        )
        row = await cur.fetchone()
        total_opps = row["total_opps"] or 0
        taken = row["taken"] or 0
        tactical_tendency = round(taken / total_opps, 4) if total_opps > 0 else 0.0

        # --- 3. Risk appetite ---
        # Average absolute cp_delta on non-blunder moves (cp_delta < 150)
        cur = await db.execute(
            """
            SELECT AVG(ABS(COALESCE(a.cp_delta, 0))) AS avg_loss
            FROM analyses a
            JOIN positions p ON p.id = a.position_id
            JOIN games g ON g.id = p.game_id
            WHERE (g.white = ? OR g.black = ?)
              AND p.is_mainline = 1
              AND ABS(COALESCE(a.cp_delta, 0)) < 150
              AND a.cp_delta IS NOT NULL
            """,
            (player, player),
        )
        row = await cur.fetchone()
        risk_appetite = round(row["avg_loss"] or 0.0, 2)

        # --- 4. Tilt index ---
        # Win rate after 0, 1, 2+ consecutive losses within same event/session
        cur = await db.execute(
            """
            WITH player_games AS (
                SELECT
                    id,
                    white,
                    black,
                    event,
                    date,
                    result,
                    ROW_NUMBER() OVER (PARTITION BY event ORDER BY date, id) AS game_seq
                FROM games
                WHERE (white = ? OR black = ?)
                  AND result IN ('1-0','0-1','1/2-1/2')
            ),
            with_prev AS (
                SELECT
                    g.id,
                    g.event,
                    g.date,
                    g.result,
                    g.game_seq,
                    CASE
                        WHEN g.result = '1-0' AND g.white = ? THEN 1
                        WHEN g.result = '0-1' AND g.black = ? THEN 1
                        WHEN g.result = '1/2-1/2' THEN 0
                        ELSE 0
                    END AS is_win,
                    CASE
                        WHEN g.result = '0-1' AND g.white = ? THEN 1
                        WHEN g.result = '1-0' AND g.black = ? THEN 1
                        ELSE 0
                    END AS is_loss
                FROM player_games g
            ),
            loss_streaks AS (
                SELECT
                    id,
                    event,
                    date,
                    game_seq,
                    is_win,
                    is_loss,
                    SUM(is_loss) OVER (
                        PARTITION BY event
                        ORDER BY game_seq
                        ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
                    ) AS losses_before
                FROM with_prev
            )
            SELECT
                AVG(CASE WHEN losses_before = 0 THEN is_win END) AS pct_after_0,
                AVG(CASE WHEN losses_before >= 1 AND losses_before < 3 THEN is_win END) AS pct_after_1_2,
                AVG(CASE WHEN losses_before >= 3 THEN is_win END) AS pct_after_3plus
            FROM loss_streaks
            """,
            (player, player, player, player, player, player),
        )
        row = await cur.fetchone()
        pct_after_0 = row["pct_after_0"] or 0.0
        pct_after_1_2 = row["pct_after_1_2"] or 0.0
        pct_after_3plus = row["pct_after_3plus"] or 0.0
        # tilt_index: positive means player performs worse after losses
        tilt_index = round(pct_after_0 - pct_after_1_2, 4) if pct_after_0 > 0 else 0.0

        # --- 5. Time pressure blunders ---
        cur = await db.execute(
            """
            SELECT
                SUM(CASE WHEN p.ply > 30 AND ABS(COALESCE(a.cp_delta, 0)) > 150 THEN 1 ELSE 0 END) AS blunders_deep,
                COUNT(CASE WHEN p.ply > 30 THEN 1 END) AS total_deep,
                SUM(CASE WHEN p.ply <= 30 AND ABS(COALESCE(a.cp_delta, 0)) > 150 THEN 1 ELSE 0 END) AS blunders_early,
                COUNT(CASE WHEN p.ply <= 30 THEN 1 END) AS total_early
            FROM analyses a
            JOIN positions p ON p.id = a.position_id
            JOIN games g ON g.id = p.game_id
            WHERE (g.white = ? OR g.black = ?)
              AND p.is_mainline = 1
              AND a.cp_delta IS NOT NULL
            """,
            (player, player),
        )
        row = await cur.fetchone()
        blunders_deep = row["blunders_deep"] or 0
        total_deep = row["total_deep"] or 1
        blunders_early = row["blunders_early"] or 0
        total_early = row["total_early"] or 1
        rate_deep = blunders_deep / total_deep
        rate_early = blunders_early / total_early
        # Ratio > 1 means more blunders under time pressure
        time_pressure_blunders = round(rate_deep / rate_early, 4) if rate_early > 0 else round(rate_deep, 4)

        # --- 6. Opening breadth (ECO-like from first 3 move patterns) ---
        cur = await db.execute(
            """
            WITH opening_keys AS (
                SELECT
                    g.id,
                    GROUP_CONCAT(p.move_san, ' ') AS opening_pattern
                FROM games g
                JOIN positions p ON p.game_id = g.id
                WHERE (g.white = ? OR g.black = ?)
                  AND p.is_mainline = 1
                  AND p.ply BETWEEN 1 AND 6
                GROUP BY g.id
            )
            SELECT COUNT(DISTINCT opening_pattern) AS distinct_openings
            FROM opening_keys
            """,
            (player, player),
        )
        row = await cur.fetchone()
        opening_breadth = row["distinct_openings"] or 0

    return ProfileAnalysisResult(
        player_name=player,
        total_games=total_games,
        tactical_tendency=tactical_tendency,
        risk_appetite=risk_appetite,
        tilt_index=tilt_index,
        time_pressure_blunders=time_pressure_blunders,
        opening_breadth=opening_breadth,
    )
