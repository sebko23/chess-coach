"""Phase 4 metric implementations (BBF-54 skeleton).

Each metric in this module follows the §B4 contract:

  1. Takes a SQLite DB path or a list of pre-fetched rows.
  2. Returns an `EffectSize` object (from effect_size.py)
     with the point estimate, Cohen's d, bootstrap CI, and
     sample size. Metrics that cannot compute (insufficient
     sample, query failure, etc.) return an `EffectSize`
     with `d=None` and `sample_size=0`.
  3. Documents hypothesis + null hypothesis in the
     docstring, per §B4 rules 1+2.
  4. Has a per-metric `MIN_SAMPLE_SIZE` constant. The
     `gate_metric()` helper from effect_size.py uses this
     to decide whether the metric can surface as a
     coaching insight.
  5. Has a corresponding section in
     `docs/15_methodology/profile-metrics-v1.md`.

## Sprint note

BBF-54 ships this module with documented stubs (the
functions raise NotImplementedError). BBF-57 extracts
the 5 existing metrics from
`services/chess_coach/gateway/routes/profile_analysis.py`
into this module with full implementations. BBF-58 adds
the 6th metric (decision_fatigue) and sequence-based
tilt. BBF-59 wires archetypes. The reason for the
stubs-and-fill-in pattern: each BBF needs to land green,
and the §B4 rigor layer is too much for one commit.
"""
from __future__ import annotations

from .effect_size import EffectSize


# --- Per-metric minimum sample sizes ---
# These are intentionally conservative defaults; the
# methodology docs (BBF-60) state the empirical basis.
# Some metrics need higher N (e.g. conversion_ability
# needs a critical mass of won positions to be meaningful).
MIN_SAMPLE_DEFAULT = 30
MIN_SAMPLE_OPENING = 20       # opening_comfort can surface with fewer games
MIN_SAMPLE_CONVERSION = 15    # conversion_ability only meaningful with N wins
MIN_SAMPLE_DECISION_FATIGUE = 50  # needs long sessions to detect


def tactical_vs_positional_bias(
    db_path: str,
    player: str,
) -> EffectSize:
    """Rate at which the player converts `>0 cp` opportunities into positive deltas.

    Hypothesis (H1): The player converts tactical
    opportunities (positions where `score_cp - prev_cp >
    80cp` from their POV) at a rate higher than 50%
    (the null = random-guess rate).

    Null hypothesis (H0): The player converts opportunities
    at the random-guess rate (50%). Cohen's d is computed
    against this null.

    Effect-size threshold: d >= 0.5 against null=0.5
    (per §B4 rule 3).

    Sample-size requirement: MIN_SAMPLE_DEFAULT (30).

    Returns `EffectSize(d=None, ..., sample_size=0)` when
    fewer than MIN_SAMPLE_DEFAULT opportunities qualify
    or when the SQL query yields no data.

    BBF-54 stub. BBF-57 implements.
    """
    raise NotImplementedError(
        "tactical_vs_positional_bias is implemented in BBF-57 -- "
        "extracted from routes/profile_analysis.py with §B4 "
        "rigor layer applied."
    )


def time_pressure_quality(
    db_path: str,
    player: str,
) -> EffectSize:
    """Difference in blunder rate between deep plies and early plies.

    Hypothesis (H1): The player makes MORE blunders (cp
    drop > 100) in deep plies (>30) than in early plies
    (<=30) -- i.e. "time pressure hurts them".

    Null hypothesis (H0): The deep-ply blunder rate equals
    the early-ply blunder rate (no time-pressure effect).
    Cohen's d is computed against null=0 (no difference).

    Sample-size requirement: MIN_SAMPLE_DEFAULT (30).

    BBF-54 stub. BBF-57 implements.
    """
    raise NotImplementedError(
        "time_pressure_quality is implemented in BBF-57."
    )


def opening_comfort(
    db_path: str,
    player: str,
) -> EffectSize:
    """Distinct count of opening move prefixes the player has played.

    Hypothesis (H1): The player has played at least K
    distinct opening patterns in their first 10 plies
    (a measure of opening repertoire breadth).

    Null hypothesis (H0): The player plays a narrow
    repertoire (K=1 or 2 openings). Cohen's d is computed
    against null=2 (a deliberately narrow default).

    Sample-size requirement: MIN_SAMPLE_OPENING (20).

    Note: this is a "breadth" metric, not a "comfort"
    metric in the strict sense -- the name is preserved
    for backward-compat with the dashboard.

    BBF-54 stub. BBF-57 implements.
    """
    raise NotImplementedError(
        "opening_comfort is implemented in BBF-57."
    )


def conversion_ability(
    db_path: str,
    player: str,
) -> EffectSize:
    """Rate at which the player converts winning positions to wins.

    Hypothesis (H1): The player converts positions where
    they were winning (score_cp > 200 from their POV at
    ply 30+) at a rate higher than the cohort mean.

    Null hypothesis (H0): The player converts winning
    positions at the random rate (the empirical cohort
    mean from the analyses table).

    Sample-size requirement: MIN_SAMPLE_CONVERSION (15
    positions must qualify -- i.e. 15 positions where
    the player had score_cp > 200 from their POV at ply
    30+).

    BBF-54 stub. BBF-57 implements. This metric does NOT
    exist in the current routes/profile_analysis.py
    (the dashboard schema lists it but the backend
    doesn't compute it).
    """
    raise NotImplementedError(
        "conversion_ability is implemented in BBF-57 -- "
        "this metric is NEW in Phase 4 finish."
    )


def blunder_rate_vs_rating(
    db_path: str,
    player: str,
) -> EffectSize:
    """Blunder rate normalized against the player's mean opponent rating.

    Hypothesis (H1): The player's blunder rate (cp drop
    > 150 per move) is lower than would be expected for
    their mean opponent rating (a "rating-relative"
    blunder rate).

    Null hypothesis (H0): The player's blunder rate is
    at the rating-expected level (a linear model from
    Lichess data, see methodology doc for the exact
    formula).

    Sample-size requirement: MIN_SAMPLE_DEFAULT (30).

    BBF-54 stub. BBF-57 implements. Like
    conversion_ability, this metric does NOT exist in the
    current routes/profile_analysis.py.
    """
    raise NotImplementedError(
        "blunder_rate_vs_rating is implemented in BBF-57 -- "
        "NEW in Phase 4 finish."
    )


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

    BBF-54 stub. BBF-58 implements.
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