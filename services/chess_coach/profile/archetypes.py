"""Archetype clustering against the L-2 gold corpus (BBF-54 skeleton).

Archetypes are user-facing labels assigned to a player based
on the cluster their metric vector falls into. The phase-plan
calls these out explicitly:

  > "Adds the 6th metric, archetype labels, sequence-based tilt."

The §B4 modification renamed the user-facing surface from
"Psychological Profiling" to "Playing Style Patterns"; the
internal module name stays `profile` (per the review).

## How archetypes work

1. Load the L-2 gold corpus (v2 in BBF-55; v1 in this BBF).
2. For each L-2 position, compute the 6 metric values using
   a fixed synthetic game history anchored at that position.
   The result is a "reference metric vector" for each L-2
   archetype (e.g. "Tactician" archetype maps to a metric
   vector with high tactical_vs_positional_bias and high
   decision_fatigue).
3. For the target player, compute their 6 metric values
   using their real game history.
4. Cluster the player's metric vector against the L-2
   reference vectors using k-nearest-neighbours (k=3) and
   assign the modal label.

## Why L-2 gold is the calibration source

The phase-plan-v2.md explicitly says Phase 4 needs "labeled
positions to validate metric effect-size thresholds". L-2
gold v2 (BBF-55) adds `eval_delta_cp` labels that make the
archetype reference vectors well-defined.

## Sprint note

BBF-54 ships this module as a documented stub. BBF-59 fills
in the actual clustering logic. The kNN implementation uses
scikit-learn if it's already a transitive dep (it is for
the embedder's cosine-similarity math); otherwise it falls
back to a pure-Python implementation.

## Why we don't expose "archetype_label" as a hard guarantee

Per §B4 rules, archetype labels are EXPERIMENTAL. They are
a clustering result, not a measurement. The dashboard
renders the label with the "experimental" badge and the
explain view links to the L-2 reference vectors that
produced the cluster assignment. The player can always
drill down to see "you were labeled Tactician because your
metric vector is closest to L2-v2-0007, L2-v2-0011, and
L2-v2-0014 -- here are the raw metric values for those
reference positions."
"""
from __future__ import annotations

from dataclasses import dataclass

from .effect_size import EffectSize


@dataclass(frozen=True)
class ArchetypeAssignment:
    """Result of clustering a player against the L-2 reference vectors.

    Attributes:
        label: The assigned archetype name (e.g. "Tactician",
            "Positional Player", "Grinder", "Wildcard",
            "Specialist"). "Unknown" when the player's
            metric vector is too far from any L-2 reference.
        nearest_neighbors: Top-k L-2 entry IDs that the
            player's metric vector is closest to. Used
            by the /explain endpoint to show methodology.
        distance: The kth-nearest-neighbor distance (lower
            = more confident assignment). Surfaced in the
            UI as a confidence indicator.
        effect_size: EffectSize for the cluster assignment
            (computed against the null = "no archetype
            match"). When this fails the §B4 gate, the
            archetype is rendered as "Inconclusive" rather
            than the assigned label.
    """

    label: str
    nearest_neighbors: list[str]
    distance: float
    effect_size: EffectSize


# Standard archetype labels. Defined here so BBF-59
# doesn't have to introduce new strings. New labels are
# added by extending this tuple and updating the
# methodology doc; backward compat is preserved by the
# string value, not the index.
STANDARD_ARCHETYPES = (
    "Tactician",        # high tactical_vs_positional_bias, low time_pressure_quality
    "Positional Player",# low tactical, low blunder_rate, high opening breadth
    "Grinder",          # high conversion_ability, low decision_fatigue
    "Wildcard",         # high opening breadth, low conversion (plays many openings, doesn't close)
    "Specialist",       # low opening breadth (1-2 openings), high conversion
    "Tilter",           # high sequence_based_tilt
    "Endgame Specialist",# low blunder_rate in deep plies
    "Unknown",          # metric vector too far from any L-2 reference
)


def cluster_archetypes(
    metrics: dict[str, float],
    l2_gold_version: str = "v2",
) -> ArchetypeAssignment:
    """Assign an archetype to a player based on their 6-metric vector.

    Args:
        metrics: Dict mapping metric_id (e.g.
            "tactical_vs_positional_bias") to the
            point-estimate float value. Missing keys
            are treated as the metric's null value.
        l2_gold_version: Which L-2 corpus version to
            use as the reference vectors. "v1" is the
            12-position seed (BBF-51); "v2" is the
            eval-delta-extended corpus (BBF-55).

    Returns:
        ArchetypeAssignment with the label, nearest
        neighbor IDs, distance, and effect size.

    BBF-54 stub. BBF-59 implements. When BBF-54 ships,
    this function raises NotImplementedError so any
    accidental import fails loudly.

    L-2 v1 (12 positions, 5 opening / 4 middlegame /
    3 endgame) is too small for archetype clustering
    (k=3 needs at least 6 reference vectors per label
    for stable assignments, but v1 has 3 source types,
    not 8 archetypes). BBF-55 grows L-2 to ~25-30
    positions with eval-delta labels so the reference
    set is large enough to be meaningful.
    """
    raise NotImplementedError(
        "cluster_archetypes is implemented in BBF-59 -- "
        "requires L-2 gold v2 (BBF-55) for reference vectors."
    )


__all__ = [
    "ArchetypeAssignment",
    "STANDARD_ARCHETYPES",
    "cluster_archetypes",
]