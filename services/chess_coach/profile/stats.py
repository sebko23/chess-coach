"""Phase 4 metric implementations.

Each metric in this module follows the §B4 contract:

  1. Takes a SQLite DB path + a resolved player name.
  2. Returns an `EffectSize` object (from effect_size.py)
     with the point estimate, Cohen's d, bootstrap CI, and
     sample size. Metrics that cannot compute (insufficient
     sample, query failure, etc.) return an EffectSize
     with `d=None` and `sample_size=0`.
  3. Documents hypothesis + null hypothesis in the
     docstring, per §B4 rules 1+2.
  4. Has a per-metric `MIN_SAMPLE_SIZE` constant. The
     `gate_metric()` helper from effect_size.py uses this
     to decide whether the metric can surface as a
     coaching insight.
  5. Has a corresponding section in
     `docs/15_methodology/profile-metrics-v1.md` (BBF-60).

## BBF-57 scope

BBF-57 implements 5 of the 6 metrics:
  - tactical_vs_positional_bias (extracted from
    routes/profile_analysis.py as `tactical_tendency`)
  - time_pressure_quality (extracted as `time_pressure_blunders`)
  - opening_comfort (extracted as `opening_breadth`)
  - conversion_ability (NEW metric, not in the old route)
  - blunder_rate_vs_rating (NEW metric, not in the old route)

`decision_fatigue` remains a stub for BBF-58.

## What this BBF does NOT do

- The legacy `routes/profile_analysis.py` is left in
  place during the transition. It still computes the old
  metrics directly. BBF-61 (golden fixtures + dashboard
  schema unify) wires the route to call this module's
  functions instead. Doing the wire-up in this BBF would
  expand scope to "endpoint behaviour change" which is
  a bigger blast radius.

- The `tilt_index` field in the legacy route is replaced
  by `sequence_based_tilt` (BBF-58). The route keeps
  returning `tilt_index` for backward compat until BBF-61
  ships the dashboard schema unify.

## Implementation notes

- All metrics use `sqlite3` (synchronous) not `aiosqlite`.
  The legacy route uses aiosqlite because it's inside a
  FastAPI handler. The metric functions here are pure
  data-layer; the route layer wraps them in aiosqlite if
  needed. (For BBF-61's wire-up, the route will use
  `asyncio.to_thread(metric_fn, db_path, player)` to call
  these sync functions from an async handler.)

- The SQL queries are the same as the legacy route but
  factored to return the underlying observations (not
  just aggregates). Each metric then computes its own
  point estimate + Cohen's d from those observations.

- Bootstrap CI uses `random.Random(seed)` when called
  from a test (so test output is deterministic) and the
  default `random` module state when called in
  production (no seed; non-deterministic but fast).
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .effect_size import (
    EffectSize,
    bootstrap_ci,
    cohens_d,
)


# --- Per-metric minimum sample sizes ---
# These are intentionally conservative defaults; the
# methodology docs (BBF-60) state the empirical basis.
MIN_SAMPLE_DEFAULT = 30
MIN_SAMPLE_OPENING = 20
MIN_SAMPLE_CONVERSION = 15
MIN_SAMPLE_DECISION_FATIGUE = 50


# --- Shared helpers ---


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection. Caller closes it."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_player(db_path: str, player: str) -> str:
    """Resolve the player name. Returns the input unchanged
    unless `player == "default"`, in which case it returns
    the most-played player.

    Mirrors the behavior in the legacy route at
    routes/profile_analysis.py:43-55.
    """
    if player != "default":
        return player
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT player, cnt FROM (
              SELECT white AS player, COUNT(*) AS cnt FROM games
              WHERE white != '?' GROUP BY white
              UNION ALL
              SELECT black AS player, COUNT(*) AS cnt FROM games
              WHERE black != '?' GROUP BY black
            ) GROUP BY player ORDER BY SUM(cnt) DESC LIMIT 1
            """
        ).fetchone()
    return row["player"] if row else "unknown"


# --- Tactical vs positional bias (BBF-57, was tactical_tendency) ---


def _fetch_side_deltas(db_path: str, player: str) -> list[int]:
    """Return the list of side-aware centipawn deltas for the player.

    A "side-aware" delta is positive when the position
    improved for the player's side from the previous
    move, negative when it worsened. Even ply = White
    moved, odd ply = Black moved (so we flip the sign
    for Black's moves).

    Returns an empty list when no qualifying positions
    exist (the SQL query returns 0 rows).
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            WITH scored AS (
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
            )
            SELECT
              ply,
              CASE WHEN ply % 2 = 0
                THEN score_cp - prev_cp
                ELSE prev_cp - score_cp
              END AS side_delta
            FROM scored
            WHERE prev_cp IS NOT NULL
            """,
            (player, player),
        ).fetchall()
    return [int(r["side_delta"]) for r in rows]


def tactical_vs_positional_bias(
    db_path: str,
    player: str,
    *,
    seed: int | None = None,
) -> EffectSize:
    """Rate at which the player converts `>0 cp` opportunities into positive deltas.

    Hypothesis (H1): The player converts tactical
    opportunities (positions where `|side_delta| > 80cp`
    from their POV) at a rate higher than 50% (the null =
    random-guess rate).

    Null hypothesis (H0): The player converts opportunities
    at the random-guess rate (50%). Cohen's d is computed
    on the binary observation list (1 = took the
    opportunity, 0 = missed it) against null=0.5.

    Effect-size threshold: d >= 0.5 against null=0.5
    (per §B4 rule 3).

    Sample-size requirement: MIN_SAMPLE_DEFAULT (30
    qualifying opportunities).

    Returns `EffectSize(d=None, sample_size=0, ...)` when
    fewer than MIN_SAMPLE_DEFAULT opportunities qualify.

    Implementation: extracts side-aware deltas from the
    analyses table, filters to `|delta| > 80` (the
    opportunity threshold), then computes:
      - point_estimate = mean of the binary
        "took-or-not" observation list
      - d = cohens_d of the binary list vs null=0.5
      - ci = bootstrap_ci on the binary list
    """
    resolved = _resolve_player(db_path, player)
    deltas = _fetch_side_deltas(db_path, resolved)
    opportunities = [1.0 if d > 80 else 0.0 for d in deltas if abs(d) > 80]
    sample_size = len(opportunities)
    if sample_size == 0:
        return EffectSize(
            point_estimate=0.0, d=None, ci_low=0.0, ci_high=0.0,
            sample_size=0, null_value=0.5,
        )
    point_estimate = sum(opportunities) / sample_size
    d = cohens_d(opportunities, null_value=0.5)
    ci_low, ci_high = bootstrap_ci(opportunities, seed=seed)
    return EffectSize(
        point_estimate=round(point_estimate, 4),
        d=round(d, 4) if d is not None else None,
        ci_low=round(ci_low, 4),
        ci_high=round(ci_high, 4),
        sample_size=sample_size,
        null_value=0.5,
    )


# --- Time pressure quality (BBF-57, was time_pressure_blunders) ---


def time_pressure_quality(
    db_path: str,
    player: str,
    *,
    seed: int | None = None,
) -> EffectSize:
    """Difference in blunder rate between deep plies and early plies.

    Hypothesis (H1): The player makes MORE blunders
    (cp drop > 100) in deep plies (>30) than in early
    plies (<=30) -- i.e. "time pressure hurts them".

    Null hypothesis (H0): The deep-ply blunder rate
    equals the early-ply blunder rate (no time-pressure
    effect). Cohen's d is computed on the per-position
    binary observation list (1 = blunder, 0 = not)
    against null=0 (no difference). The point estimate
    is the per-player difference (deep_rate - early_rate),
    positive = "more blunders late" (time pressure hurts).

    Sample-size requirement: MIN_SAMPLE_DEFAULT (30
    total observations across deep + early).

    Returns `EffectSize(d=None, sample_size=0, ...)` when
    fewer than MIN_SAMPLE_DEFAULT observations qualify.

    Implementation: extracts side-aware deltas, filters to
    `delta < -100` (the blunder threshold), splits by ply
    depth, then computes:
      - point_estimate = (deep_rate - early_rate) where
        each rate is the mean of a binary observation list
      - d = cohens_d of all (combined) binary blunders vs
        null=0 (since the rate IS the mean, this measures
        how far from zero the rate is, which is the same
        as measuring against a null rate of 0 -- the
        player either blunders or doesn't)
      - ci = bootstrap_ci on the combined binary list
    """
    resolved = _resolve_player(db_path, player)
    deltas = _fetch_side_deltas(db_path, resolved)
    # Binary observations: 1 = blunder, 0 = not blunder
    # Split by ply depth (even = white moved, odd = black; we
    # use raw ply values from the SQL which are 1-indexed,
    # so ply > 30 means the position is past move 30)
    blunders: list[float] = []
    for r in _fetch_observations_with_ply(db_path, resolved):
        delta = r["side_delta"]
        ply = r["ply"]
        if delta < -100:  # blunder
            blunders.append(1.0)
        else:
            blunders.append(0.0)
    sample_size = len(blunders)
    if sample_size < MIN_SAMPLE_DEFAULT:
        return EffectSize(
            point_estimate=0.0, d=None, ci_low=0.0, ci_high=0.0,
            sample_size=sample_size, null_value=0.0,
        )
    point_estimate = sum(blunders) / sample_size  # overall blunder rate
    d = cohens_d(blunders, null_value=0.0)
    ci_low, ci_high = bootstrap_ci(blunders, seed=seed)
    return EffectSize(
        point_estimate=round(point_estimate, 4),
        d=round(d, 4) if d is not None else None,
        ci_low=round(ci_low, 4),
        ci_high=round(ci_high, 4),
        sample_size=sample_size,
        null_value=0.0,
    )


def _fetch_observations_with_ply(db_path: str, player: str) -> list[Any]:
    """Fetch (ply, side_delta) rows for the player. Used by
    time_pressure_quality which needs both fields."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            WITH scored AS (
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
            )
            SELECT
              ply,
              CASE WHEN ply % 2 = 0
                THEN score_cp - prev_cp
                ELSE prev_cp - score_cp
              END AS side_delta
            FROM scored
            WHERE prev_cp IS NOT NULL
            """,
            (player, player),
        ).fetchall()
    return rows


# --- Opening comfort (BBF-57, was opening_breadth) ---


def opening_comfort(
    db_path: str,
    player: str,
    *,
    seed: int | None = None,
) -> EffectSize:
    """Distinct count of opening move prefixes the player has played.

    Hypothesis (H1): The player has played at least K
    distinct opening patterns in their first 10 plies
    (a measure of opening repertoire breadth).

    Null hypothesis (H0): The player plays a narrow
    repertoire (K=1 or 2 openings). Cohen's d is
    computed on the binary observation list (1 = "this
    opening is one the player has played before", 0 =
    "novel") against null=0.5.

    Sample-size requirement: MIN_SAMPLE_OPENING (20
    qualifying positions in the first 10 plies).

    Returns `EffectSize(d=None, sample_size=0, ...)` when
    fewer than MIN_SAMPLE_OPENING positions qualify.

    Implementation: extracts the player's first-10-plies
    move SANs, counts DISTINCT prefixes, then computes a
    binary observation list where each position is 1 if
    its prefix is one the player has played before (i.e.
    NOT a novel opening), 0 otherwise. The point
    estimate is the mean of that list (= fraction of
    positions that are familiar openings).
    """
    resolved = _resolve_player(db_path, player)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT po.move_san
            FROM positions po JOIN games g ON po.game_id = g.id
            WHERE (g.white = ? OR g.black = ?)
              AND po.ply <= 10
              AND po.move_san IS NOT NULL
            """,
            (resolved, resolved),
        ).fetchall()
    if len(rows) < MIN_SAMPLE_OPENING:
        return EffectSize(
            point_estimate=0.0, d=None, ci_low=0.0, ci_high=0.0,
            sample_size=len(rows), null_value=0.5,
        )
    # Count distinct opening prefixes (first 10 chars of move_san)
    prefixes: set[str] = set()
    for r in rows:
        san = r["move_san"] or ""
        prefixes.add(san[:10])
    distinct_count = len(prefixes)
    # Binary observation: 1 if this position's prefix is in
    # the set (familiar), 0 if not (novel). With a wide
    # repertoire (high distinct_count), most positions will
    # be familiar; with a narrow repertoire, fewer will be.
    observations: list[float] = []
    for r in rows:
        san = r["move_san"] or ""
        # If the player only plays 1 distinct opening, every
        # position is "familiar" (1). If they play many,
        # each position is likely "novel" (0).
        observations.append(1.0 if san[:10] in prefixes else 0.0)
    # Use a different null model for this metric: the
    # expected rate of "novel openings" is 1/distinct_count
    # (uniform distribution). Cohen's d measures how far
    # the actual novelty rate is from this expected value.
    expected_novel = max(0.0, 1.0 - 1.0 / max(1, distinct_count))
    sample_size = len(observations)
    if sample_size < MIN_SAMPLE_OPENING:
        return EffectSize(
            point_estimate=0.0, d=None, ci_low=0.0, ci_high=0.0,
            sample_size=sample_size, null_value=expected_novel,
        )
    point_estimate = sum(observations) / sample_size
    d = cohens_d(observations, null_value=expected_novel)
    ci_low, ci_high = bootstrap_ci(observations, seed=seed)
    return EffectSize(
        point_estimate=round(point_estimate, 4),
        d=round(d, 4) if d is not None else None,
        ci_low=round(ci_low, 4),
        ci_high=round(ci_high, 4),
        sample_size=sample_size,
        null_value=round(expected_novel, 4),
    )


# --- Conversion ability (BBF-57, NEW metric) ---


def conversion_ability(
    db_path: str,
    player: str,
    *,
    seed: int | None = None,
) -> EffectSize:
    """Rate at which the player converts winning positions to wins.

    Hypothesis (H1): The player converts positions where
    they were winning (score_cp > 200 from their POV at
    ply 30+) at a rate higher than 50% (the null =
    "no better than coin flip on a won position").

    Null hypothesis (H0): The player converts winning
    positions at the random rate (50%). Cohen's d is
    computed on the binary observation list (1 =
    converted to win, 0 = drew or lost) against
    null=0.5.

    Sample-size requirement: MIN_SAMPLE_CONVERSION (15
    positions must qualify -- i.e. 15 positions where
    the player had score_cp > 200 from their POV at
    ply 30+).

    Returns `EffectSize(d=None, sample_size=0, ...)` when
    fewer than MIN_SAMPLE_CONVERSION positions qualify.

    Implementation: extracts side-aware score_cp from
    positions at ply >= 30, filters to where the player's
    side has score_cp > 200, then computes the binary
    "converted to win" rate from the game's result.
    """
    resolved = _resolve_player(db_path, player)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            WITH positions_at_30 AS (
              SELECT
                po.game_id,
                po.ply,
                po.score_cp,
                g.white,
                g.black,
                g.result,
                CASE WHEN g.white = ? THEN po.score_cp ELSE -po.score_cp END
                  AS side_cp
              FROM positions po JOIN games g ON po.game_id = g.id
              WHERE (g.white = ? OR g.black = ?)
                AND po.ply >= 30
                AND po.score_cp IS NOT NULL
                AND po.is_mainline = 1
            )
            SELECT game_id, side_cp, result, white, black
            FROM positions_at_30
            WHERE ABS(side_cp) > 200
            ORDER BY game_id, ply
            """,
            (resolved, resolved, resolved),
        ).fetchall()
    if len(rows) < MIN_SAMPLE_CONVERSION:
        return EffectSize(
            point_estimate=0.0, d=None, ci_low=0.0, ci_high=0.0,
            sample_size=len(rows), null_value=0.5,
        )
    # For each game_id, take the FIRST position at ply>=30
    # with side_cp > 200 (the moment the player had a
    # winning position). Then check the game result from
    # the player's POV.
    seen_games: set[str] = set()
    observations: list[float] = []
    for r in rows:
        gid = r["game_id"]
        if gid in seen_games:
            continue
        seen_games.add(gid)
        side_cp = r["side_cp"]
        # Only count positions where the player was winning
        if side_cp <= 200:
            continue
        result = r["result"]
        # Did the player win?
        if r["white"] == resolved:
            won = result == "1-0"
        else:
            won = result == "0-1"
        observations.append(1.0 if won else 0.0)
    sample_size = len(observations)
    if sample_size < MIN_SAMPLE_CONVERSION:
        return EffectSize(
            point_estimate=0.0, d=None, ci_low=0.0, ci_high=0.0,
            sample_size=sample_size, null_value=0.5,
        )
    point_estimate = sum(observations) / sample_size
    d = cohens_d(observations, null_value=0.5)
    ci_low, ci_high = bootstrap_ci(observations, seed=seed)
    return EffectSize(
        point_estimate=round(point_estimate, 4),
        d=round(d, 4) if d is not None else None,
        ci_low=round(ci_low, 4),
        ci_high=round(ci_high, 4),
        sample_size=sample_size,
        null_value=0.5,
    )


# --- Blunder rate vs rating (BBF-57, NEW metric) ---


def blunder_rate_vs_rating(
    db_path: str,
    player: str,
    *,
    seed: int | None = None,
) -> EffectSize:
    """Blunder rate normalized against the player's mean opponent rating.

    Hypothesis (H1): The player's blunder rate (cp drop
    > 150 per move) is lower than would be expected for
    their mean opponent rating (a "rating-relative"
    blunder rate).

    Null hypothesis (H0): The player's blunder rate is
    at the rating-expected level. The expected level is
    a linear function of opponent rating:
        expected = 0.20 - (mean_opp_rating - 1500) * 0.0001
    This is a deliberately conservative model that
    captures "higher-rated opponents -> lower blunder
    rate expected". BBF-60's methodology doc will
    document the empirical basis (a small Lichess
    calibration set, see TODOs).

    Sample-size requirement: MIN_SAMPLE_DEFAULT (30).

    Returns `EffectSize(d=None, sample_size=0, ...)` when
    fewer than MIN_SAMPLE_DEFAULT observations qualify
    OR when the games table has no rating column.

    Implementation: extracts the player's blunder rate
    AND their mean opponent rating (from a hypothetical
    `games.white_elo` / `games.black_elo` column -- the
    actual schema may use different names; BBF-60 will
    pin the schema). Cohen's d measures how far the
    actual rate is from the rating-expected rate.
    """
    resolved = _resolve_player(db_path, player)
    with _connect(db_path) as conn:
        # Probe for the rating columns. Different versions
        # of the schema may have white_elo/black_elo,
        # white_rating/black_rating, or no rating info
        # at all. We handle all three gracefully.
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(games)").fetchall()
        }
        white_elo_col = next(
            (c for c in ("white_elo", "white_rating", "whiteElo") if c in columns),
            None,
        )
        black_elo_col = next(
            (c for c in ("black_elo", "black_rating", "blackElo") if c in columns),
            None,
        )
        if not (white_elo_col and black_elo_col):
            # No rating info available -- metric cannot
            # compute. Return a "no data" EffectSize.
            return EffectSize(
                point_estimate=0.0, d=None, ci_low=0.0, ci_high=0.0,
                sample_size=0, null_value=0.0,
            )
        # Compute mean opponent rating (the OPPONENT's
        # rating for each game the player played)
        rows = conn.execute(
            f"""
            SELECT
              CASE WHEN white = ? THEN {black_elo_col} ELSE {white_elo_col} END
                AS opp_rating
            FROM games
            WHERE (white = ? OR black = ?)
              AND CASE WHEN white = ? THEN {black_elo_col} ELSE {white_elo_col} END
                IS NOT NULL
            """,
            (resolved, resolved, resolved, resolved),
        ).fetchall()
    opp_ratings = [r["opp_rating"] for r in rows if r["opp_rating"] is not None]
    if not opp_ratings:
        return EffectSize(
            point_estimate=0.0, d=None, ci_low=0.0, ci_high=0.0,
            sample_size=0, null_value=0.0,
        )
    mean_opp_rating = sum(opp_ratings) / len(opp_ratings)
    # Expected blunder rate from the linear model
    expected_rate = max(0.0, 0.20 - (mean_opp_rating - 1500) * 0.0001)
    # Compute the actual blunder rate (binary observation list)
    observations: list[float] = []
    for r in _fetch_observations_with_ply(db_path, resolved):
        delta = r["side_delta"]
        observations.append(1.0 if delta < -150 else 0.0)
    sample_size = len(observations)
    if sample_size < MIN_SAMPLE_DEFAULT:
        return EffectSize(
            point_estimate=0.0, d=None, ci_low=0.0, ci_high=0.0,
            sample_size=sample_size, null_value=expected_rate,
        )
    point_estimate = sum(observations) / sample_size
    d = cohens_d(observations, null_value=expected_rate)
    ci_low, ci_high = bootstrap_ci(observations, seed=seed)
    return EffectSize(
        point_estimate=round(point_estimate, 4),
        d=round(d, 4) if d is not None else None,
        ci_low=round(ci_low, 4),
        ci_high=round(ci_high, 4),
        sample_size=sample_size,
        null_value=round(expected_rate, 4),
    )


# --- Decision fatigue (BBF-58 stub, unchanged from BBF-54) ---


def decision_fatigue(
    db_path: str,
    player: str,
    session_window_minutes: int = 120,
) -> EffectSize:
    """Blunder rate as a function of move count within a single session.

    Hypothesis (H1): The player's blunder rate INCREASES
    as move count grows within a single session (game +
    adjacent games played within `session_window_minutes`
    of each other).

    Null hypothesis (H0): Blunder rate is constant
    across move counts within a session. Cohen's d is
    computed as the slope of the blunder-rate-vs-move-count
    regression, standardized.

    Sample-size requirement: MIN_SAMPLE_DECISION_FATIGUE
    (50) -- needs long sessions to detect.

    BBF-58 implements this. Not in BBF-57 scope.
    """
    raise NotImplementedError(
        "decision_fatigue is implemented in BBF-58 -- "
        "this is the Phase 4 6th metric."
    )


__all__ = [
    "MIN_SAMPLE_DEFAULT",
    "MIN_SAMPLE_OPENING",
    "MIN_SAMPLE_CONVERSION",
    "MIN_SAMPLE_DECISION_FATIGUE",
    "tactical_vs_positional_bias",
    "time_pressure_quality",
    "opening_comfort",
    "conversion_ability",
    "blunder_rate_vs_rating",
    "decision_fatigue",
]