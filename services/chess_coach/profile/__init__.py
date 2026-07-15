"""Playing Style Patterns (Phase 4, BBF-54..62 sprint).

This package implements the Phase 4 metrics and archetype
labels per the v2 phase-plan and the §B4 statistical-rigor
rules from `docs/13_review_response/response-to-review.md`.

## §B4 rules (from the Claude review, accepted in Phase 4 prep)

Every metric in this package MUST provide:

  1. **Hypothesis** -- a one-sentence statement of what
     the metric is supposed to measure.
  2. **Null hypothesis** -- what value would be observed
     if the player has no measurable tendency in this
     dimension.
  3. **Effect-size threshold** -- Cohen's d >= 0.5 against
     the null distribution. Below-threshold metrics MUST
     NOT be surfaced as coaching insights, regardless of
     p-value.
  4. **Sample-size requirement** -- the metric refuses to
     return a value when fewer than N positions qualify
     (the "I don't have enough data" state).
  5. **Confidence band** -- the metric returns a 95%
     bootstrap CI alongside the point estimate, so the
     UI can render uncertainty.
  6. **Methodology doc** -- every metric has a
     corresponding section in
     `docs/15_methodology/profile-metrics-v1.md`.

## Sprint sequencing

This package is the result of a multi-BBF sprint:

  BBF-54  package skeleton + pyproject registration
  BBF-55  test xfail-tracking pattern (the BBF-54 tests
          were too strict for the BBF-54 intent)
  BBF-56  1-character typo fix from BBF-55
  BBF-57  5 of 6 metric implementations + cohens_d +
          bootstrap_ci (this commit)
  BBF-58  decision_fatigue (6th metric) + sequence-based
          tilt
  BBF-59  archetype clustering against L-2 v2
  BBF-60  /v1/profile/{player}/explain/{metric} endpoint
          + methodology docs
  BBF-61  golden fixtures + dashboard schema unify
  BBF-62  frontend rewrite (badge + disclaimer +
          /explain drill-down UI)

## The 6 metrics

The 6 metrics tracked by this package (per the phase-plan
exit criteria):

  1. tactical_vs_positional_bias -- count of `>0` deltas
     in opportunities, normalized.
  2. time_pressure_quality -- blunder rate (cp drop
     > 100) -- binary observation per position.
  3. opening_comfort -- DISTINCT count of opening move
     prefixes the player has played.
  4. conversion_ability -- rate at which the player
     converts winning positions (cp > 200 from POV at
     ply 30+) to wins.
  5. blunder_rate_vs_rating -- blunder rate normalized
     against the player's mean opponent rating (a
     rating-relative blunder rate).
  6. decision_fatigue -- blunder rate as a function of
     move count within a single session (Phase 4 6th
     metric, BBF-58).
"""
from __future__ import annotations

# Public API. BBF-57 re-exports the 5 implemented metrics.
# BBF-58 will re-export decision_fatigue and sequence_based_tilt.
# BBF-59 will re-export cluster_archetypes.

from .effect_size import (
    EffectSize,
    COHENS_D_THRESHOLD,
    bootstrap_ci,
    cohens_d,
    gate_metric,
)
from .stats import (
    tactical_vs_positional_bias,
    time_pressure_quality,
    opening_comfort,
    conversion_ability,
    blunder_rate_vs_rating,
    # decision_fatigue -- NOT re-exported in BBF-57; lands
    # in BBF-58.
)

__all__: list[str] = [
    # stats.py -- BBF-57 implementations (5 of 6)
    "tactical_vs_positional_bias",
    "time_pressure_quality",
    "opening_comfort",
    "conversion_ability",
    "blunder_rate_vs_rating",
    # effect_size.py -- BBF-57 implementations
    # (re-exported so callers can use `gate_metric()` from
    # the package level)
    "cohens_d",
    "bootstrap_ci",
    "gate_metric",
    "EffectSize",
    "COHENS_D_THRESHOLD",
    # stats.py -- BBF-58 stubs (NOT re-exported yet)
    # "decision_fatigue",
    # "sequence_based_tilt",
    # archetypes.py -- BBF-59 stub (NOT re-exported yet)
    # "cluster_archetypes",
]