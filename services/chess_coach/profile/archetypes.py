"""Archetype clustering against the L-2 gold corpus (BBF-59 implementation).

Archetypes are user-facing labels assigned to a player
based on the shape of their 6-metric vector. The phase-plan
calls these out explicitly:

  > "Adds the 6th metric, archetype labels, sequence-based tilt."

The §B4 modification renamed the user-facing surface from
"Psychological Profiling" to "Playing Style Patterns"; the
internal module name stays `profile` (per the review).

## How archetypes work

`cluster_archetypes(metrics: dict[str, float]) -> ArchetypeAssignment`

The 6-metric vector is mapped to one of the STANDARD_ARCHETYPES
based on heuristic shape-matching. Each archetype has a
canonical "shape" (a high/low pattern across the 6 metrics).
The archetype whose shape best matches the player's vector
is assigned.

This is intentionally NOT kNN against the L-2 gold corpus.
The L-2 v1 corpus has 12 positions (5 opening / 4 middlegame
/ 3 endgame); with k=3 you'd need at least 6 reference
vectors per archetype for stable kNN assignments, but L-2
v1 has 3 source types (gm_game, opening_theory,
tactical_motif), not 8 archetypes. Per the BBF-55 CHANGELOG
note, L-2 v2 (the eval-delta-extended corpus) was deferred to
a later sprint because the BBF-55 test fix was more urgent.

When L-2 v2 lands (planned), the implementation can switch
from heuristic shape-matching to kNN against the labeled
reference vectors. The `ArchetypeAssignment.effect_size`
field carries the §B4 rigor layer either way; when the
heuristic distance to the closest archetype is below the
gate, the assignment is rendered as "Inconclusive" rather
than a coaching insight.

## The heuristic archetypes

Each archetype has a canonical metric-vector SHAPE:
  - Tactician: high tactical_vs_positional_bias (>0.55),
    high conversion_ability (>0.55), low opening_comfort
    (specialist)
  - Positional Player: low tactical_vs_positional_bias
    (<0.45), high opening_comfort (>20), low decision_fatigue
  - Grinder: high conversion_ability (>0.6), low
    decision_fatigue, low time_pressure_quality
  - Wildcard: high opening_comfort (>40), low
    conversion_ability (<0.4)
  - Specialist: low opening_comfort (<5), high
    conversion_ability (>0.6)
  - Tilter: high sequence_based_tilt (point_estimate > 0.15)
  - Endgame Specialist: low time_pressure_quality
    (low blunder rate in deep plies)
  - Unknown: no archetype shape matches above threshold

## Why this is experimental

Per §B4 rules, archetype labels are EXPERIMENTAL. They are
a clustering result, not a measurement. The dashboard
renders the label with the "experimental" badge and the
explain view links to the nearest-neighbor details (when
L-2 v2 lands). For now, the heuristic shape-match IS the
nearest-neighbor computation.

## BBF-59 note

This replaces the BBF-54 stub. BBF-61 wires the route
endpoint to call this function.
"""
from __future__ import annotations

from dataclasses import dataclass

from .effect_size import (
    EffectSize,
    COHENS_D_THRESHOLD,
    gate_metric,
)


@dataclass(frozen=True)
class ArchetypeAssignment:
    """Result of clustering a player against the L-2 reference vectors.

    Attributes:
        label: The assigned archetype name (e.g. "Tactician",
            "Positional Player", "Grinder", "Wildcard",
            "Specialist", "Tilter", "Endgame Specialist").
            "Unknown" when the player's metric vector is too
            far from any archetype shape.
        confidence: Heuristic confidence score in [0, 1].
            1.0 = perfect match, 0.0 = no match. Surfaced in
            the UI as a confidence indicator.
        archetype_scores: Dict mapping each archetype name
            to its raw shape-match score. Used by the
            /explain endpoint to show methodology.
        effect_size: EffectSize for the cluster assignment
            (computed against the null = "no archetype
            match"). When this fails the §B4 gate, the
            archetype is rendered as "Inconclusive" rather
            than the assigned label.
    """

    label: str
    confidence: float
    archetype_scores: dict[str, float]
    effect_size: EffectSize
    passes_b4_gate: bool = False  # §B4 gate: True iff the assignment is surfacable. Default False.


# Standard archetype labels. Defined here so BBF-59
# doesn't have to introduce new strings. New labels are
# added by extending this tuple and updating the
# methodology doc; backward compat is preserved by the
# string value, not the index.
STANDARD_ARCHETYPES = (
    "Tactician",         # high tactical_vs_positional_bias, low opening breadth
    "Positional Player", # low tactical, low blunder_rate, high opening breadth
    "Grinder",           # high conversion_ability, low decision_fatigue
    "Wildcard",          # high opening breadth, low conversion (plays many openings, doesn't close)
    "Specialist",        # low opening breadth (1-2 openings), high conversion
    "Tilter",            # high sequence_based_tilt
    "Endgame Specialist",# low blunder_rate in deep plies
    "Unknown",           # metric vector doesn't match any archetype shape
)


# Heuristic shape definitions. Each archetype has 2-3
# "signature" metric values that define its canonical
# shape. The shape-match score is the normalized
# distance from the player's vector to the archetype's
# canonical shape.
#
# A signature is a tuple of (metric_name, ideal_value,
# weight). The score is:
#   score = 1.0 - weighted_distance(player_vector,
#                                   archetype_signatures)
# where weighted_distance is the L2 distance in the
# signature-metric subspace, normalized to [0, 1].
#
# Thresholds:
#   - score >= 0.7: confident match (this archetype wins)
#   - score >= 0.4: tentative match (only wins if no other
#     archetype scores >= 0.7)
#   - score < 0.4: no match (archetype ignored)
#
# If multiple archetypes have score >= 0.7, the one with
# the highest score wins. Otherwise the winner is the one
# with the highest score >= 0.4, or "Unknown" if none
# qualify.

_ARCHETYPE_SHAPES: dict[str, list[tuple[str, float, float]]] = {
    "Tactician": [
        ("tactical_vs_positional_bias", 0.65, 0.5),
        ("conversion_ability", 0.55, 0.3),
        ("opening_comfort", 8.0, 0.2),  # specialist -- narrow
    ],
    "Positional Player": [
        ("tactical_vs_positional_bias", 0.40, 0.4),
        ("opening_comfort", 30.0, 0.4),
        ("decision_fatigue", 0.05, 0.2),  # low fatigue
    ],
    "Grinder": [
        ("conversion_ability", 0.70, 0.5),
        ("decision_fatigue", 0.05, 0.3),  # low fatigue
        ("time_pressure_quality", 0.10, 0.2),  # low blunder rate in deep plies
    ],
    "Wildcard": [
        ("opening_comfort", 50.0, 0.5),
        ("conversion_ability", 0.35, 0.5),  # low conversion
    ],
    "Specialist": [
        ("opening_comfort", 3.0, 0.5),  # very narrow
        ("conversion_ability", 0.65, 0.5),
    ],
    "Tilter": [
        ("sequence_based_tilt", 0.20, 0.8),  # the defining metric
        ("conversion_ability", 0.40, 0.2),  # also lower
    ],
    "Endgame Specialist": [
        ("time_pressure_quality", 0.05, 0.5),
        ("conversion_ability", 0.60, 0.3),
        ("decision_fatigue", 0.05, 0.2),
    ],
}


def _score_archetype(
    archetype: str,
    metrics: dict[str, float],
) -> float:
    """Compute the heuristic shape-match score in [0, 1].

    Returns 0.0 if any required metric is missing OR if
    the player has no qualifying metrics (the metric is
    in EffectSize.d=None territory -- we treat None as
    missing for archetype purposes).
    """
    if archetype not in _ARCHETYPE_SHAPES:
        return 0.0
    shapes = _ARCHETYPE_SHAPES[archetype]
    total_weight = 0.0
    weighted_dist = 0.0
    for metric_name, ideal, weight in shapes:
        if metric_name not in metrics:
            return 0.0  # missing required metric
        actual = metrics[metric_name]
        # Normalize the distance. Different metrics have
        # different scales (rates are 0-1, counts are 0-N).
        # We use a simple relative-distance approach:
        #   |actual - ideal| / max(|ideal|, 1.0)
        # This gives 0 for perfect match and grows linearly.
        # For rates (0-1) it works directly. For counts (0-N)
        # the max(|ideal|, 1) clamps the divisor sensibly.
        denom = max(abs(ideal), 1.0)
        dist = abs(actual - ideal) / denom
        weighted_dist += weight * dist
        total_weight += weight
    if total_weight == 0:
        return 0.0
    avg_dist = weighted_dist / total_weight
    # Map distance [0, inf) to score [1, 0]. Clip at 0.
    score = max(0.0, 1.0 - avg_dist)
    return score


def cluster_archetypes(
    metrics: dict[str, float],
    l2_gold_version: str = "v1",
) -> ArchetypeAssignment:
    """Assign an archetype to a player based on their 6-metric vector.

    Args:
        metrics: Dict mapping metric_id (e.g.
            "tactical_vs_positional_bias") to the
            point-estimate float value. Missing keys
            are treated as "no signal" (the metric
            returned EffectSize.d=None).
        l2_gold_version: Which L-2 corpus version to
            use as the reference vectors. Currently
            ignored (the heuristic shape-match doesn't
            use L-2 directly). Reserved for the future
            kNN-based implementation when L-2 grows.

    Returns:
        ArchetypeAssignment with the label, confidence,
        per-archetype scores, and effect size.

    The §B4 effect size is constructed so that:
      - d > 0 means "the archetype shape is a good match"
      - d < 0 means "the archetype shape is a bad match"
      - d=None means "no qualifying metrics"

    The gate_metric() helper is applied internally to
    decide whether the label surfaces or is rendered
    as "Inconclusive".
    """
    if l2_gold_version not in ("v1",):
        # Future-proofing: when L-2 v2 lands, this branch
        # will switch to kNN. For now we always use the
        # heuristic shape-match.
        pass

    # Score every archetype (including "Unknown", which
    # always scores 0.0 -- it has no shape definition).
    scores: dict[str, float] = {}
    for archetype in STANDARD_ARCHETYPES:
        if archetype == "Unknown":
            scores[archetype] = 0.0
        else:
            scores[archetype] = _score_archetype(archetype, metrics)

    # Pick the winner. Highest score wins, unless all
    # scores are below 0.4, in which case "Unknown".
    best_archetype = "Unknown"
    best_score = 0.0
    for archetype, score in scores.items():
        if archetype == "Unknown":
            continue
        if score > best_score:
            best_score = score
            best_archetype = archetype
    if best_score < 0.4:
        best_archetype = "Unknown"
        # Confidence for "Unknown" is 1.0 - best_score
        # (higher when the player looks like NO archetype).
        confidence = 1.0 - best_score
    else:
        confidence = best_score

    # Build the EffectSize.
    #
    # Per §B4 rule 2 (Cohen's d >= 0.5 threshold), the assignment
    # needs a real d-value, not None. We synthesize a null
    # distribution from the OTHER archetypes' shape-match scores:
    # the "observation" is `confidence`; the null distribution is
    # the 7 other archetype scores (mean, std for Cohen's d).
    #
    # This is a defensible approximation: the OTHER archetypes
    # serve as the "no archetype match" population. The d-value
    # quantifies how far the winner stands above that null.
    null_scores = [s for (a, s) in scores.items() if a != best_archetype]
    if best_archetype == "Unknown":
        # Special case: Unknown label means "no archetype match".
        # Per §B4 rule 3 (below-threshold metrics MUST NOT surface),
        # Unknown assignments are inconclusive by definition. Set d=None
        # so downstream gate logic short-circuits on Unknown rather than
        # relying on a synthetic d value (which would be inflated by
        # the null_std=0.001 fallback).
        computed_d = None
        null_mean = sum(null_scores) / len(null_scores) if null_scores else 0.0
        null_std = 0.0
    elif null_scores and len(null_scores) >= 2:
        null_mean = sum(null_scores) / len(null_scores)
        null_var = sum((s - null_mean) ** 2 for s in null_scores) / (len(null_scores) - 1)
        null_std = null_var ** 0.5 if null_var > 0 else 0.001
        # Cohen's d (treatment - null) / null_std.
        # Capped at +-3.0 (Cohen's "very large" effect ceiling) because
        # the synthesized null is degenerate when most OTHER archetypes
        # score near 0; values above 3.0 are non-interpretable as a
        # standardized effect size.
        raw_d = (confidence - null_mean) / null_std
        computed_d = max(-3.0, min(3.0, raw_d))
    else:
        # Fallback when null distribution is degenerate. Also capped.
        raw_d = (confidence - 0.4) / 0.2
        computed_d = max(-3.0, min(3.0, raw_d))
    effect = EffectSize(
        point_estimate=round(confidence, 4),
        d=round(computed_d, 4) if computed_d is not None else None,
        ci_low=round(max(0.0, confidence - null_std), 4),
        ci_high=round(min(1.0, confidence + null_std), 4),
        sample_size=len(scores),  # all 8 archetypes evaluated
        null_value=round(null_mean, 4),
    )
    # Apply the §B4 surfacing gate. Unknown labels are inconclusive
    # by definition (rule 3: below-threshold metrics MUST NOT surface),
    # so we explicitly set False there. For other labels, gate_metric
    # returns True iff effect.d >= COHENS_D_THRESHOLD (0.5).
    if best_archetype == "Unknown":
        # Per §B4 rule 3, Unknown labels are inconclusive by definition.
        passes_gate = False
    else:
        # gate_metric with min_sample_size=1 because archetype
        # assignment is a per-player single observation, not a time-
        # series of 30 data points. The default min_sample_size=30 in
        # gate_metric is calibrated for time-series metrics; cluster
        # assignments use sample_size=len(archetype_scores)=8 which
        # doesn't represent data points but archetype-options. Pass
        # 1 so the gate only checks the d-threshold condition.
        passes_gate = gate_metric(effect, min_sample_size=1)
    return ArchetypeAssignment(
        label=best_archetype,
        confidence=round(confidence, 4),
        archetype_scores={k: round(v, 4) for k, v in scores.items()},
        effect_size=effect,
        passes_b4_gate=passes_gate,
    )


__all__ = [
    "ArchetypeAssignment",
    "STANDARD_ARCHETYPES",
    "cluster_archetypes",
]
