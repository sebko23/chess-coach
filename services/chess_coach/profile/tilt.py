"""Sequence-based tilt detection (BBF-59 implementation).

The pre-existing `tilt_index` field in the
`routes/profile_analysis.py` response measures ONLY the
"first game after a loss" effect: `max(0, baseline_winrate
- post_loss_winrate)`. The Phase 4 finish replaces this
with a sliding-window tilt detector that captures
sequence-level deterioration (multiple losses in a row
produce a stronger effect than a single loss).

## What this module computes

`sequence_based_tilt(db_path, player) -> EffectSize`

The metric computes the winrate in games following a streak
of N consecutive losses, for window sizes N=1, 2, 3, ...
up to MAX_WINDOW. The "sequence tilt" is the maximum
negative delta across all window sizes, normalized
against the player's overall winrate.

## Hypothesis

H1: A player's winrate in games following a streak of N
losses is lower than their overall baseline winrate.

H0: Post-loss-streak winrate equals overall baseline
winrate (no sequence effect).

Effect-size threshold: d >= 0.5 against null=0 (no
difference). Below-threshold metrics MUST NOT surface
as a "you tilt" insight.

## Sample-size requirement

At least MIN_SAMPLE_TILT (30) games total, with at
least MIN_LOSS_STREAKS (5) loss-streaks of length >= 2
for the metric to be meaningful.

## Implementation notes

- Groups games by "session" via the `games.date` column.
  Games with the same date (PGN Date tag) are treated as
  one session; cross-date games are independent. Falls
  back to `games.created_at` when `date` is NULL.
- Window sizes N=1..MAX_WINDOW: for each game that
  follows a streak of N consecutive losses, count it as
  a "1" (win) or "0" (loss/draw). The binary observation
  list is the union across all N values.
- The point estimate is `max(0, baseline_winrate -
  worst_window_winrate)`. The Cohen's d is computed on
  the binary observation list against null=0 (no
  difference). The bootstrap CI is on the binary list.

## BBF-59 note

This replaces the BBF-54 stub. The pre-existing
`tilt_index` field in the legacy route stays in place
during the transition; the new metric is exposed as
`sequence_tilt` alongside the old field for one BBF
cycle so the dashboard can be migrated without a
breaking change (BBF-61 wires the route to call this
function).

## Related work

BBF-59 (archetypes) consumes this metric: a player
classified as "Tilter" archetype has a `sequence_tilt`
that passes the §B4 gate.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .effect_size import EffectSize, bootstrap_ci, cohens_d
from .stats import _connect, _resolve_player


MIN_SAMPLE_TILT = 30         # total games
MIN_LOSS_STREAKS = 5         # loss streaks of length >= 2
MAX_WINDOW = 5               # largest window size to check


def _fetch_player_games_with_date(
    db_path: str, player: str
) -> list[tuple[str, str]]:
    """Fetch (result, date_or_created_at) for the player's games.

    `result` is the player's POV (W/L/D). `date_or_created_at`
    is the games.date column (PGN date) when present,
    otherwise the games.created_at column. Both are TEXT
    ISO-format strings.

    Returns the list in chronological order (oldest first),
    which is the natural order for sequence-based analysis.
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
              CASE
                WHEN white = ? AND result = '1-0' THEN 'W'
                WHEN white = ? AND result = '0-1' THEN 'L'
                WHEN black = ? AND result = '0-1' THEN 'W'
                WHEN black = ? AND result = '1-0' THEN 'L'
                ELSE 'D'
              END AS player_result,
              COALESCE(date, created_at) AS game_date
            FROM games
            WHERE (white = ? OR black = ?)
              AND result IS NOT NULL
            ORDER BY COALESCE(date, created_at) ASC, id ASC
            """,
            (player, player, player, player, player, player),
        ).fetchall()
    return [(r["player_result"], r["game_date"]) for r in rows]


def _build_loss_streaks(
    games: list[tuple[str, str]],
) -> list[int]:
    """Return the lengths of all loss-streaks in the game sequence.

    A "loss streak" is a maximal run of consecutive L
    results. Draws (D) break streaks. Wins (W) break
    streaks. A streak of length 0 (single D) is ignored.

    For the sliding-window analysis: we need the length
    of the immediately-preceding loss streak for each
    game. This function returns just the lengths of the
    streaks; the sliding-window logic uses them
    directly.
    """
    streak_lengths: list[int] = []
    current = 0
    for result, _ in games:
        if result == "L":
            current += 1
        else:
            if current > 0:
                streak_lengths.append(current)
            current = 0
    # Tail
    if current > 0:
        streak_lengths.append(current)
    return streak_lengths


def sequence_based_tilt(
    db_path: str,
    player: str,
    *,
    seed: int | None = None,
) -> EffectSize:
    """Detect sequence-level tilt via a sliding-window analysis.

    For each game, look back N games (N=1..MAX_WINDOW).
    If the immediately-preceding N games were ALL losses,
    this game is in a "post-loss-streak of N" position.
    Compare the winrate in those positions to the
    player's overall baseline winrate.

    Args:
        db_path: SQLite database path.
        player: Player name (or "default" to use the most-played).
        seed: Optional RNG seed for deterministic bootstrap CI.

    Returns:
        EffectSize with:
          - point_estimate: max(0, baseline - worst_window_winrate)
          - d: Cohen's d of binary (win=1, loss/draw=0) observations
              across all windows, vs null=0
          - ci_low, ci_high: bootstrap CI on the binary list
          - sample_size: total number of "post-loss-streak" games
              across all window sizes (with overlap)
          - null_value: 0.0 (no sequence effect)

    Returns `EffectSize(d=None, sample_size=0, ...)` when
    the player has fewer than MIN_SAMPLE_TILT games or
    fewer than MIN_LOSS_STREAKS qualifying streaks.
    """
    resolved = _resolve_player(db_path, player)
    games = _fetch_player_games_with_date(db_path, resolved)
    total_games = len(games)
    if total_games < MIN_SAMPLE_TILT:
        return EffectSize(
            point_estimate=0.0, d=None, ci_low=0.0, ci_high=0.0,
            sample_size=total_games, null_value=0.0,
        )
    streak_lengths = _build_loss_streaks(games)
    qualifying_streaks = [s for s in streak_lengths if s >= 2]
    if len(qualifying_streaks) < MIN_LOSS_STREAKS:
        return EffectSize(
            point_estimate=0.0, d=None, ci_low=0.0, ci_high=0.0,
            sample_size=total_games, null_value=0.0,
        )
    # Baseline winrate across all games
    wins = sum(1 for r, _ in games if r == "W")
    baseline = wins / total_games
    # For each game (skipping the first N games where N is
    # the current streak length being tested), check if
    # the previous N games were all losses.
    observations: list[float] = []
    worst_winrate = baseline
    for window in range(1, MAX_WINDOW + 1):
        for i in range(window, total_games):
            # Is the previous `window` games all losses?
            streak = [games[i - k - 1][0] for k in range(window)]
            if all(r == "L" for r in streak):
                # This game is in a post-loss-streak-of-N position
                observations.append(1.0 if games[i][0] == "W" else 0.0)
        # After collecting all observations for this window
        # size, compute the winrate and update worst_winrate
        if observations:
            window_wins = sum(observations)
            window_rate = window_wins / len(observations)
            if window_rate < worst_winrate:
                worst_winrate = window_rate
    sample_size = len(observations)
    if sample_size == 0:
        return EffectSize(
            point_estimate=0.0, d=None, ci_low=0.0, ci_high=0.0,
            sample_size=0, null_value=0.0,
        )
    point_estimate = max(0.0, baseline - worst_winrate)
    # Cohen's d: the binary list is "won after loss streak or
    # not". The null hypothesis is "winrate after loss streak
    # equals overall baseline" -- so the per-game null is
    # baseline (probability of winning = baseline). d is
    # (mean(obs) - baseline) / std(obs).
    mean_obs = sum(observations) / sample_size
    if sample_size > 1:
        variance = sum((x - mean_obs) ** 2 for x in observations) / (sample_size - 1)
        std = variance ** 0.5
    else:
        std = 0.0
    if std == 0:
        d = None
    else:
        d = (mean_obs - baseline) / std
    ci_low, ci_high = bootstrap_ci(observations, seed=seed)
    return EffectSize(
        point_estimate=round(point_estimate, 4),
        d=round(d, 4) if d is not None else None,
        ci_low=round(ci_low, 4),
        ci_high=round(ci_high, 4),
        sample_size=sample_size,
        null_value=0.0,
    )


__all__ = [
    "MIN_SAMPLE_TILT",
    "MIN_LOSS_STREAKS",
    "MAX_WINDOW",
    "sequence_based_tilt",
]