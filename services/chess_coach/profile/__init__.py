"""Playing Style Patterns (Phase 4, BBF-54..62 sprint).

This package implements the Phase 4 metrics and archetype
labels per the v2 phase-plan and the §B4 statistical-rigor
rules from `docs/13_review_response/response-to-review.md`.

## §B4 rules (from the Claude review, accepted in Phase 4 prep)

Every metric in this package MUST provide:

  1. **Hypothesis** — a one-sentence statement of what the
     metric is supposed to measure.
  2. **Null hypothesis** — what value would be observed if
     the player has no measurable tendency in this dimension.
  3. **Effect-size threshold** — Cohen's d >= 0.5 against the
     null distribution. Below-threshold metrics MUST NOT be
     surfaced as coaching insights, regardless of p-value.
  4. **Sample-size requirement** — the metric refuses to
     return a value when fewer than N positions qualify
     (the "I don't have enough data" state).
  5. **Confidence band** — the metric returns a 95% bootstrap
     CI alongside the point estimate, so the UI can render
     uncertainty.
  6. **Methodology doc** — every metric has a corresponding
     section in `docs/15_methodology/profile-metrics-v1.md`.

The package's modules are wired up as:

  stats.py        -- the 6 metric implementations
  effect_size.py  -- shared Cohen's d + bootstrap CI helpers
  archetypes.py   -- clustering against the L-2 gold corpus
  tilt.py         -- sequence-based tilt detection (BBF-58)

The route layer (`services/chess_coach/gateway/routes/
profile.py`) consumes this package via the public API in
`__all__`. Tests live in `tests/unit/test_profile_stats.py`
and `tests/unit/test_profile_archetypes.py` (added in later
BBFs).

## Sprint sequencing

This package is the result of a multi-BBF sprint:

  BBF-54  -- package skeleton + pyproject registration
            (this commit)
  BBF-55  -- L-2 gold v2 with eval-delta labels
  BBF-56  -- effect_size.py -- Cohen's d + bootstrap CI
  BBF-57  -- extract 5 existing metrics into stats.py with
            §B4 rigor layer
  BBF-58  -- 6th metric (decision_fatigue) + sequence-based tilt
  BBF-59  -- archetype clustering against L-2 v2
  BBF-60  -- /v1/profile/{player}/explain/{metric} endpoint
  BBF-61  -- golden fixtures + dashboard schema unify
  BBF-62  -- frontend rewrite (badge + disclaimer + /explain UI)

BBF-54 only creates the package skeleton with empty (but
documented) submodules. Subsequent BBFs fill in the
implementations.

## The 6 metrics

The 6 metrics tracked by this package (per the phase-plan
exit criteria):

  1. tactical_vs_positional_bias -- count of `>0` deltas in
     opportunities, normalized (currently `tactical_tendency`
     in the old route).
  2. time_pressure_quality -- blunder rate differential
     between early and deep plies (currently
     `time_pressure_blunders` in the old route).
  3. opening_comfort -- DISTINCT count of opening prefixes
     the player has played (currently `opening_breadth`).
  4. conversion_ability -- rate at which the player converts
     winning positions to wins (currently not computed --
     pre-existing field in the dashboard schema).
  5. blunder_rate_vs_rating -- blunder rate normalized
     against the player's mean opponent rating (currently
     not computed -- the old `blunder_count` is a flat count).
  6. decision_fatigue -- blunder rate as a function of move
     count within a single session (Phase 4 6th metric).
"""
from __future__ import annotations

# Public API. Filled in by subsequent BBFs.
# BBF-54 ships an empty skeleton; the next BBFs will add:
#   from .stats import (
#       tactical_vs_positional_bias,
#       time_pressure_quality,
#       opening_comfort,
#       conversion_ability,
#       blunder_rate_vs_rating,
#       decision_fatigue,
#   )
#   from .effect_size import cohens_d, bootstrap_ci
#   from .archetypes import cluster_archetypes
#   from .tilt import sequence_based_tilt

__all__: list[str] = [
    # stats.py (BBF-57, BBF-58)
    "tactical_vs_positional_bias",
    "time_pressure_quality",
    "opening_comfort",
    "conversion_ability",
    "blunder_rate_vs_rating",
    "decision_fatigue",
    # effect_size.py (BBF-56)
    "cohens_d",
    "bootstrap_ci",
    # archetypes.py (BBF-59)
    "cluster_archetypes",
    # tilt.py (BBF-58)
    "sequence_based_tilt",
]