"""Statistical rigor helpers for Phase 4 metrics.

This module is the §B4 "effect-size + bootstrap CI" substrate
used by every metric in `stats.py`. It exists separately from
`stats.py` so the metric implementations and the statistical
primitives can be tested independently.

## §B4 rules this module implements

Every metric in the Phase 4 sprint must report:

  - **Cohen's d** -- standardized effect size of the
    observation list against a fixed null value.
    d >= 0.5 is the "worth surfacing" threshold (medium
    effect per Cohen 1988).
  - **Bootstrap CI** -- 95% confidence interval around the
    point estimate, so the UI can render uncertainty.
  - **Below-threshold gate** -- metrics with d < 0.5 OR
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

## BBF-57 implementation note

BBF-56 was originally scoped to implement `cohens_d` and
`bootstrap_ci` standalone. BBF-56 (the typo-fix commit)
ended up only fixing the BBF-55 test typo, so the
primitives stayed as stubs. BBF-57 implements both
primitives here, alongside the metric implementations,
per the BBF-21 discipline ("fix all known dep gaps in
one BBF").
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class EffectSize:
    """Result of a metric computation with §B4 statistical rigor.

    Attributes:
        point_estimate: The metric value (e.g. tactical
            tendency = 0.62 meaning "62% of opportunities
            taken"). This is what the UI displays.
        d: Cohen's d of the observation list against the
            null value. `None` when the sample size is below
            the gate OR when the sample has zero variance
            (no meaningful effect-size measurement).
        ci_low: Bootstrap 95% CI lower bound on the
            point_estimate.
        ci_high: Bootstrap 95% CI upper bound on the
            point_estimate.
        sample_size: Number of observations the metric
            computed over.
        null_value: The expected value under the null
            hypothesis (used for d calculation).
    """

    point_estimate: float
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

    Returns `None` when:
      - The sample has fewer than 2 elements (no variance
        can be computed).
      - The sample has zero variance (std == 0).

    Cohen 1988 thresholds:
        d < 0.2  -- negligible
        0.2..0.5 -- small
        0.5..0.8 -- medium  (← Phase 4 surfacing threshold)
        >= 0.8   -- large

    The returned `d` is signed: positive when the sample
    mean is HIGHER than the null value, negative when
    LOWER. The §B4 gate uses `abs(d) >= threshold` so the
    direction doesn't matter for surfacing.
    """
    if len(sample) < 2:
        return None
    mean = sum(sample) / len(sample)
    variance = sum((x - mean) ** 2 for x in sample) / (len(sample) - 1)
    std = variance ** 0.5
    if std == 0:
        return None
    return (mean - null_value) / std


def bootstrap_ci(
    sample: list[float],
    statistic: str = "mean",
    n_resamples: int = 1000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float]:
    """Return a bootstrap CI for the given statistic.

    Args:
        sample: The observations.
        statistic: "mean" or "median" (extensible later).
        n_resamples: Number of bootstrap iterations. 1000
            is the standard "good enough" value
            (Efron & Tibshirani 1993).
        confidence: 0.95 for a 95% CI.
        seed: Optional RNG seed for deterministic test
            output. When `None`, the default `random`
            module state is used (NOT seeded; tests should
            pass a seed for reproducibility).

    Returns:
        (ci_low, ci_high) percentiles from the bootstrap
            distribution of the chosen statistic.

    Implementation:
        - Resample with replacement `n_resamples` times.
        - Compute the statistic for each resample.
        - Sort the statistics.
        - Return the alpha/2 and (1-alpha/2) percentiles
          (linear interpolation for the percentiles; not
          the "nearest rank" method).

    Uses Python stdlib only (random.choice for resampling,
    statistics.quantiles for percentile calculation). No
    scipy/numpy dependency.
    """
    if not sample:
        return (0.0, 0.0)

    rng = random.Random(seed) if seed is not None else random
    n = len(sample)
    resampled_stats: list[float] = []
    for _ in range(n_resamples):
        # Resample with replacement
        resample = [sample[rng.randint(0, n - 1)] for _ in range(n)]
        if statistic == "mean":
            resampled_stats.append(sum(resample) / n)
        elif statistic == "median":
            sorted_rs = sorted(resample)
            mid = n // 2
            if n % 2 == 1:
                resampled_stats.append(float(sorted_rs[mid]))
            else:
                resampled_stats.append((sorted_rs[mid - 1] + sorted_rs[mid]) / 2.0)
        else:
            raise ValueError(f"Unknown statistic: {statistic!r}")

    resampled_stats.sort()
    # Compute percentiles via linear interpolation
    alpha = (1.0 - confidence) / 2.0
    lo_idx = alpha * (n_resamples - 1)
    hi_idx = (1.0 - alpha) * (n_resamples - 1)
    lo_floor = int(lo_idx)
    hi_floor = int(hi_idx)
    lo_frac = lo_idx - lo_floor
    hi_frac = hi_idx - hi_floor
    ci_low = resampled_stats[lo_floor] * (1.0 - lo_frac) + resampled_stats[min(lo_floor + 1, n_resamples - 1)] * lo_frac
    ci_high = resampled_stats[hi_floor] * (1.0 - hi_frac) + resampled_stats[min(hi_floor + 1, n_resamples - 1)] * hi_frac
    return (ci_low, ci_high)


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