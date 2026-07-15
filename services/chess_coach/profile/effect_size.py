"""Statistical rigor helpers for Phase 4 metrics.

This module is the §B4 "effect-size + bootstrap CI" substrate
used by every metric in `stats.py`. It exists separately from
`stats.py` so the metric implementations and the statistical
primitives can be tested independently.

## §B4 rules this module implements

Every metric in the Phase 4 sprint must report:

  - **Cohen's d** — standardized effect size against the
    null distribution. d >= 0.5 is the "worth surfacing"
    threshold (medium effect per Cohen 1988).
  - **Bootstrap CI** — 95% confidence interval around the
    point estimate, so the UI can render uncertainty.
  - **Below-threshold gate** — metrics with d < 0.5 OR
    insufficient sample size MUST NOT be surfaced as
    coaching insights, regardless of p-value. The
    `gate_metric()` helper enforces this.

## Why this is separate from stats.py

The 6 metric implementations are domain-specific (they
know about chess, about the analyses table, about FEN).
Cohen's d + bootstrap CI are pure statistical primitives.
Splitting them lets the stats.py implementations stay
focused on the chess semantics, and lets us test the
statistical primitives against known fixtures (e.g.
"d of two identical distributions = 0.0") without setting
up chess data.

## Sprint note

BBF-54 ships this module as a documented skeleton (the
functions raise `NotImplementedError`). BBF-56 fills in
the actual implementations. The skeleton exists so that
`from chess_coach.profile.effect_size import cohens_d`
imports cleanly for downstream BBFs (and so that
`gateway-boot` CI proves the package shape).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EffectSize:
    """Result of an effect-size measurement.

    Attributes:
        d: Cohen's d (standardized mean difference).
            `None` when the sample size is below the gate.
        ci_low: Bootstrap 95% CI lower bound on the point
            estimate the metric produces.
        ci_high: Bootstrap 95% CI upper bound.
        sample_size: Number of observations the metric
            computed over.
        null_value: The expected value under the null
            hypothesis (used for d calculation).
    """

    d: float | None
    ci_low: float
    ci_high: float
    sample_size: int
    null_value: float


# §B4 rule 3: below-threshold metrics MUST NOT surface as
# coaching insights, regardless of p-value. The threshold is
# Cohen's d >= 0.5 (medium effect). Anything below is "not
# enough signal" and the UI renders the metric as
# "insufficient evidence" rather than as a coaching point.
COHENS_D_THRESHOLD = 0.5

# Default minimum sample size. Some metrics may override
# this with a higher requirement (the methodology docs will
# state the per-metric sample-size requirement).
DEFAULT_MIN_SAMPLE_SIZE = 30


def cohens_d(
    sample: list[float],
    null_value: float,
) -> float | None:
    """Compute Cohen's d against a fixed null value.

    `d = (mean(sample) - null_value) / std(sample)`.

    Returns `None` when the sample is empty or has zero
    variance (no meaningful effect-size measurement).

    Cohen 1988 thresholds:
        d < 0.2  -- negligible
        0.2..0.5 -- small
        0.5..0.8 -- medium  (← Phase 4 surfacing threshold)
        >= 0.8   -- large

    BBF-54 ships this as a NotImplementedError stub. BBF-56
    implements it (with tests against known-fixture data:
    e.g. d of [1,2,3] against null=2.0 == 0.0).
    """
    raise NotImplementedError(
        "cohens_d is implemented in BBF-56 -- see "
        "docs/15_methodology/profile-metrics-v1.md for the "
        "spec, and tests/unit/test_effect_size.py for the "
        "fixtures (BBF-56 also adds the test)."
    )


def bootstrap_ci(
    sample: list[float],
    statistic: str = "mean",
    n_resamples: int = 1000,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Return a bootstrap CI for the given statistic.

    Args:
        sample: The observations.
        statistic: "mean" or "median" (extensible later).
        n_resamples: Number of bootstrap iterations. 1000 is
            the standard "good enough" value (Efron &
            Tibshirani 1993).
        confidence: 0.95 for a 95% CI.

    Returns:
        (ci_low, ci_high) percentiles from the bootstrap
        distribution.

    BBF-54 ships this as a NotImplementedError stub. BBF-56
    implements it using Python stdlib only (random.choice
    for resampling) -- no scipy/numpy dependency unless the
    math requires it (it doesn't for percentile-of-means).
    """
    raise NotImplementedError(
        "bootstrap_ci is implemented in BBF-56 -- see "
        "tests/unit/test_effect_size.py for fixtures."
    )


def gate_metric(
    effect: EffectSize,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    d_threshold: float = COHENS_D_THRESHOLD,
) -> bool:
    """Return True iff the metric passes the §B4 surfacing gate.

    A metric passes the gate when:
      - sample_size >= min_sample_size, AND
      - d is not None (i.e. sample had nonzero variance), AND
      - |d| >= d_threshold.

    UI: when this returns False, the metric MUST be rendered
    as "insufficient evidence" rather than as a coaching
    insight. See §B4 rule 3.

    BBF-54 ships this as a working gate (it doesn't need
    statistical primitives; it operates on a precomputed
    `EffectSize` object). BBF-56 wires it to real
    cohens_d + bootstrap_ci results.
    """
    if effect.d is None:
        return False
    if effect.sample_size < min_sample_size:
        return False
    return abs(effect.d) >= d_threshold


__all__ = [
    "EffectSize",
    "COHENS_D_THRESHOLD",
    "DEFAULT_MIN_SAMPLE_SIZE",
    "cohens_d",
    "bootstrap_ci",
    "gate_metric",
]