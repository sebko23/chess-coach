"""Archetype clustering against the archetype gold corpus (BBF-66).

Replaces the BBF-59 heuristic shape-matcher with kNN classification
against the reference corpus at tests/gold/archetypes/v*/corpus.json.

## Design

The BBF-66 implementation is kNN (k=3, z-scored Euclidean) against the
v0 production corpus (see tests/gold/archetypes/v0/corpus.json
for provenance and the explicit _metadata.WARNING block). Heuristic shape-matching
(BBF-59 ship) is RETIRED entirely -- not kept as a fallback -- so there
is exactly one source of truth.

Steps:
1. Load corpus entries (label, metrics) from the configured archetype corpus.
2. Compute per-dimension mean and std from the corpus.
3. Z-score the input metrics using corpus mean/std.
4. For each corpus entry, compute the z-scored Euclidean distance
   to the input (using only dimensions present in BOTH vectors).
5. Find the k=3 nearest neighbours; majority-vote their labels.
6. If the k neighbours' mean distance > 2.0 z-score threshold,
   return label="Unknown".
7. Otherwise, return the majority label, confidence = 1 -
   (mean_distance / threshold).

## §B4 contract (preserved from BBF-65.2)

The ArchetypeAssignment includes `passes_b4_gate`, the canonical gate
field. The route at services/chess_coach/gateway/routes/profile.py:367
reads this field (per BBF-65.3). Unknown labels always set
passes_b4_gate=False (per §B4 rule 3: below-threshold metrics MUST NOT
surface). For other labels, gate_metric is called with
CLUSTER_MIN_SAMPLE_SIZE=1 (cluster assignments are single observations).

## Corpus-label caveat

The production default is the v0 auto-derived plus shape-curated corpus.
Its labels and confidence values are not externally validated against
real-player ground truth. The v1 corpus remains the bootstrap reference
used by the auto-curator. The kNN algorithm itself is correct; corpus-label
quality remains a separate data-governance concern.

## Why this was changed (BBF-59 -> BBF-66)

The BBF-59 heuristic had hard-coded shape definitions per archetype.
This meant:
  - Adding a new archetype required changing the heuristic code.
  - The shape definitions did not have a rigorous provenance.
  - Two sources of truth emerged over time (heuristic + manually
    tweaked thresholds in the route).

The kNN approach consolidates to a single reference corpus that the
domain expert (the user) can curate without touching the algorithm.
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass

from .effect_size import (
    EffectSize,
    gate_metric,
)

# BBF-66 Q4: lifted to a module constant so the gate_metric call site
# reads it explicitly. Cluster assignments are single observations
# (per-player), not time-series. The default min_sample_size=30 in
# gate_metric is calibrated for time-series metrics; cluster assignments
# use sample_size=len(archetype_scores)=8 which represents
# archetype-options, not data points, so we pass 1 to make the gate
# only check the d-threshold condition.
CLUSTER_MIN_SAMPLE_SIZE = 1


@dataclass(frozen=True)
class ArchetypeAssignment:
    """Result of clustering a player against the archetype gold corpus.

    Attributes:
        label: The assigned archetype name (e.g. "Tactician",
            "Positional Player", "Grinder", "Wildcard",
            "Specialist", "Tilter", "Endgame Specialist").
            "Unknown" when the player's metric vector is too
            far from any reference vector (mean k-nearest distance
            > z-score threshold).
        confidence: kNN-derived confidence in [0, 1].
            1.0 = perfect match (the input equals a corpus entry
            exactly), 0.0 = no overlap. Computed as
            1 - (mean_neighbor_distance / z_score_threshold),
            clamped to [0, 1]. Surfaced in the UI as a confidence
            indicator.
        archetype_scores: Dict mapping each archetype name
            to its vote-share from the k nearest neighbours
            (count of votes divided by k). Used by the
            /explain endpoint to show methodology.
        effect_size: EffectSize for the cluster assignment
            (computed against the null = "no archetype match").
            When this fails the section-B4 gate, the archetype
            is rendered as "Inconclusive" rather than the
            assigned label.
        passes_b4_gate: Canonical section-B4 gate flag. True iff
            the assignment is surfacable. The route at
            services/chess_coach/gateway/routes/profile.py:367
            reads this field (per BBF-65.3). Unknown labels always
            set this to False.
    """

    label: str
    confidence: float
    archetype_scores: dict[str, float]
    effect_size: EffectSize
    passes_b4_gate: bool = False
    # section-B4 gate: True iff the assignment is surfacable. Default False.


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


def resolve_archetype_gold_version(env: dict[str, str] | None = None) -> str:
    """Return the archetype corpus version used by production clustering."""
    src = os.environ if env is None else env
    value = src.get("CHESS_COACH_ARCHETYPE_GOLD_VERSION")
    return value if value else "v0"


def _load_corpus_entries(
    version: str | None = None,
) -> list[tuple[str, dict[str, float]]]:
    """Load the configured archetype gold corpus.

    The production default is v0, which is the corpus copied by the Docker
    image. ``CHESS_COACH_ARCHETYPE_GOLD_VERSION`` may select another
    shipped version without changing the classifier implementation.
    """
    from chess_coach.datasets.archetype_gold import load_archetype_gold

    selected_version = version or resolve_archetype_gold_version()
    return [
        (e.archetype_label, dict(e.metrics))
        for e in load_archetype_gold(selected_version)
    ]


def _zscore_normalize(
    values: Iterable[float],
    mean: Iterable[float],
    std: Iterable[float],
) -> list[float]:
    """Per-dimension z-score. Avoid division by zero (std=0 -> 0.0)."""
    out: list[float] = []
    for v, m, s in zip(values, mean, std, strict=False):
        if s > 0:
            out.append((v - m) / s)
        else:
            out.append(0.0)
    return out


def _knn_classify(
    metrics: dict[str, float],
    k: int = 3,
    z_score_threshold: float = 2.0,
    min_confidence: float = 0.3,
    corpus_version: str | None = None,
) -> tuple[str, float, dict[str, float], float]:
    """k-NN against the archetype gold corpus.

    Steps:
    1. Load corpus entries (label, metrics).
    2. Compute per-dimension mean and std from the corpus.
    3. Z-score the input metrics using corpus mean/std.
    4. For each corpus entry, compute the z-scored Euclidean distance
       to the input (using only dimensions present in BOTH vectors).
    5. Find the k nearest neighbors; majority-vote their labels.
    6. If the k neighbors' mean distance > z_score_threshold,
       return label="Unknown" (the input is too far from any archetype).
    7. Otherwise, compute confidence = 1 - (mean / threshold),
       clamped to [0, 1]. If confidence < min_confidence (default
       0.3), return "Unknown" instead of the wrong-but-close label.
       (BBF-86.5: this gates the silent failure mode where users
       in the Tactician/Wildcard/Specialist cluster (no training
       data in the original v0 bootstrap subset) get nearest-neighbor labels
       from the 4 covered archetypes. The kNN was finding "close
       enough" matches but the labels were wrong. The 0.3 floor
       is conservative: any label with confidence < 0.3 is surfaced
       as Unknown instead of being reported as authoritative.)
    8. Otherwise, return the majority label with confidence.

    Returns: (label, confidence, archetype_scores, mean_neighbor_distance)

    BBF-86.5: the `min_confidence` parameter (default 0.3) is a
    tunable gate. The threshold origin is documented as a
    heuristic; no held-out real-player validation has been
    performed. A future BBF should validate against held-out
    data. Until then, the default is conservative: any label
    with confidence < 0.3 is surfaced as Unknown instead of
    being reported as authoritative.
    """
    corpus = _load_corpus_entries(corpus_version)
    if not corpus:
        # No corpus: fall back to Unknown. (We don't have heuristic as fallback
        # per the BBF-66 design decision: heuristic is RETIRED.)
        return ("Unknown", 0.0, {}, float("inf"))

    # Determine metric dimensions present across the corpus.
    all_dimensions = sorted({m for _, mvec in corpus for m in mvec})
    if not all_dimensions:
        return ("Unknown", 0.0, {}, float("inf"))

    # Per-dimension mean/std from corpus.
    corpus_by_dim: dict[str, list[float]] = {d: [] for d in all_dimensions}
    for _, mvec in corpus:
        for d in all_dimensions:
            if d in mvec:
                corpus_by_dim[d].append(mvec[d])
    mean = [sum(corpus_by_dim[d]) / len(corpus_by_dim[d]) for d in all_dimensions]
    var = [
        sum((v - m) ** 2 for v in corpus_by_dim[d]) / max(1, len(corpus_by_dim[d]) - 1)
        for d, m in zip(all_dimensions, mean, strict=False)
    ]
    std = [v ** 0.5 for v in var]

    # Z-score the input. Missing dimensions in the input: treat as 0
    # (== at-mean after z-scoring).
    input_z: list[float] = []
    for d, m, s in zip(all_dimensions, mean, std, strict=False):
        if d in metrics:
            input_z.append((metrics[d] - m) / s if s > 0 else 0.0)
        else:
            input_z.append(0.0)  # missing-dim = at-mean

    # Z-score each corpus entry (same dimensions; missing dims in the
    # entry are treated as at-mean). Compute distance using only
    # dimensions present in BOTH input and entry.
    distances: list[tuple[str, float]] = []
    dim_index = {d: i for i, d in enumerate(all_dimensions)}
    for label, mvec in corpus:
        entry_z: list[float] = []
        for d, m, s in zip(all_dimensions, mean, std, strict=False):
            if d in mvec:
                entry_z.append((mvec[d] - m) / s if s > 0 else 0.0)
            else:
                entry_z.append(0.0)
        # Distance: squared Euclidean, restricted to dims present in BOTH.
        sq_dist = 0.0
        n_dims = 0
        for d in all_dimensions:
            if d in metrics and d in mvec:
                i_in = dim_index[d]
                sq_dist += (input_z[i_in] - entry_z[i_in]) ** 2
                n_dims += 1
        # If no dims overlap, distance is max.
        if n_dims == 0:
            distances.append((label, float("inf")))
        else:
            distances.append((label, (sq_dist / n_dims) ** 0.5))  # normalized

    # Sort by distance; take k nearest.
    distances.sort(key=lambda x: x[1])
    k_nearest = distances[:k]
    if not k_nearest:
        return ("Unknown", 0.0, {}, float("inf"))
    effective_k = len(k_nearest)
    mean_neighbor_distance = sum(d for _, d in k_nearest) / effective_k

    # Majority vote on labels among k nearest.
    label_votes: dict[str, int] = {}
    for label, _ in k_nearest:
        label_votes[label] = label_votes.get(label, 0) + 1
    winner = max(label_votes.items(), key=lambda x: x[1])[0]

    # Build archetype_scores: vote-share for each label among k nearest.
    archetype_scores = dict.fromkeys(STANDARD_ARCHETYPES, 0.0)
    for label, _ in k_nearest:
        archetype_scores[label] += 1.0 / effective_k

    # If k nearest are too far, return Unknown.
    if mean_neighbor_distance > z_score_threshold:
        return (
            "Unknown",
            max(0.0, min(1.0, 1.0 - mean_neighbor_distance / (z_score_threshold * 2))),
            archetype_scores,
            mean_neighbor_distance,
        )

    # Confidence: 1 - (mean_distance / threshold), clamped to [0, 1].
    confidence = max(0.0, min(1.0, 1.0 - (mean_neighbor_distance / z_score_threshold)))

    # BBF-86.5: gate the label by confidence. If the winner's
    # confidence is below the floor, return "Unknown" instead of
    # the wrong-but-close label. The kNN would otherwise return
    # the nearest-neighbor label for users in the
    # Tactician/Wildcard/Specialist cluster (no training data
    # in the original v0 bootstrap subset), even when the match is genuinely
    # poor (high distance, low confidence). The min_confidence
    # gate prevents this silent failure mode.
    if confidence < min_confidence:
        return ("Unknown", confidence, archetype_scores, mean_neighbor_distance)

    return (winner, confidence, archetype_scores, mean_neighbor_distance)


def cluster_archetypes(
    metrics: dict[str, float],
) -> ArchetypeAssignment:
    """Assign an archetype to a player based on their 6-metric vector.

    BBF-66: replaced BBF-59 heuristic shape-matching with kNN against the
    configured archetype gold corpus.
    Heuristic is RETIRED (not kept as a fallback) per the Q1 strategic
    decision -- single source of truth.

    Args:
        metrics: Dict mapping metric_id (e.g.
            "tactical_vs_positional_bias") to the
            point-estimate float value. Missing keys
            are treated as "no signal" (the metric
            returned EffectSize.d=None) and reduce the
            kNN's per-entry overlap dimension count.

    Returns:
        ArchetypeAssignment with the label, confidence,
        per-archetype scores, effect size, and
        passes_b4_gate flag. The label is one of
        STANDARD_ARCHETYPES (8 values).

    The section-B4 effect size is constructed so that:
      - d > 0 means "the archetype shape is a good match"
      - d < 0 means "the archetype shape is a bad match"
      - d=None means "no qualifying metrics" (Unknown label)

    The gate_metric() helper is applied internally to
    decide whether the label surfaces or is rendered
    as "Inconclusive".
    """
    label, confidence, archetype_scores, mean_distance = _knn_classify(metrics)

    # Build the EffectSize. Same BBF-65.1 logic: synthesized-null d.
    if label == "Unknown":
        computed_d = None
        null_mean = 0.0
        null_std = 0.0
    else:
        null_scores = [s for (a, s) in archetype_scores.items() if a != label]
        if null_scores and len(null_scores) >= 2:
            null_mean = sum(null_scores) / len(null_scores)
            null_var = sum((s - null_mean) ** 2 for s in null_scores) / (len(null_scores) - 1)
            null_std = null_var ** 0.5 if null_var > 0 else 0.001
            raw_d = (confidence - null_mean) / null_std
        else:
            null_mean = 0.0
            null_std = 0.001
            raw_d = (confidence - 0.4) / 0.2
        # BBF-65.1 cap: +-3.0 (Cohen's "very large" effect ceiling).
        # The synthesized null is degenerate when most OTHER archetypes
        # score near 0; values above 3.0 are non-interpretable as a
        # standardized effect size.
        computed_d = max(-3.0, min(3.0, raw_d))

    effect = EffectSize(
        point_estimate=round(confidence, 4),
        d=round(computed_d, 4) if computed_d is not None else None,
        ci_low=round(max(0.0, confidence - null_std), 4),
        ci_high=round(min(1.0, confidence + null_std), 4),
        sample_size=len(archetype_scores),
        null_value=round(null_mean, 4),
    )
    # Apply the section-B4 surfacing gate. Unknown labels are inconclusive
    # by definition (rule 3: below-threshold metrics MUST NOT surface),
    # so we explicitly set False there. For other labels, gate_metric
    # returns True iff effect.d >= COHENS_D_THRESHOLD (0.5).
    if label == "Unknown":
        # Per section-B4 rule 3, Unknown labels are inconclusive by definition.
        passes_gate = False
    else:
        # gate_metric with min_sample_size=CLUSTER_MIN_SAMPLE_SIZE because
        # archetype assignment is a per-player single observation, not a
        # time-series of 30 data points. The default min_sample_size=30
        # in gate_metric is calibrated for time-series metrics; cluster
        # assignments use sample_size=len(archetype_scores)=8 which
        # doesn't represent data points but archetype-options. Pass
        # CLUSTER_MIN_SAMPLE_SIZE=1 so the gate only checks the
        # d-threshold condition.
        passes_gate = gate_metric(effect, min_sample_size=CLUSTER_MIN_SAMPLE_SIZE)
    return ArchetypeAssignment(
        label=label,
        confidence=round(confidence, 4),
        archetype_scores={k: round(v, 4) for k, v in archetype_scores.items()},
        effect_size=effect,
        passes_b4_gate=passes_gate,
    )


__all__ = [
    "ArchetypeAssignment",
    "STANDARD_ARCHETYPES",
    "resolve_archetype_gold_version",
    "CLUSTER_MIN_SAMPLE_SIZE",
    "cluster_archetypes",
]
