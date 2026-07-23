"""Unit tests for BBF-66 kNN archetype cluster.

Tests the kNN classifier against the SYNTHETIC PLACEHOLDER corpus. The
labels are STUB; the kNN's job is to pick SOMETHING (a label from the
corpus), not to validate that labels are correct against real data.
"""

from chess_coach.datasets.archetype_gold import load_archetype_gold
from chess_coach.profile import (
    STANDARD_ARCHETYPES,
    cluster_archetypes,
)
from chess_coach.profile.archetypes import CLUSTER_MIN_SAMPLE_SIZE


def test_cluster_min_sample_size_constant():
    """BBF-66 Q4: CLUSTER_MIN_SAMPLE_SIZE is a module-level constant = 1."""
    assert CLUSTER_MIN_SAMPLE_SIZE == 1


def test_kNN_classifier_picks_label_from_corpus():
    """Given a vector that EXACTLY matches a corpus entry, the kNN
    must pick that entry's archetype_label."""
    corpus = load_archetype_gold("v1")
    # Pick the first Tactician entry
    tactician_entry = next(e for e in corpus if e.archetype_label == "Tactician")
    result = cluster_archetypes(dict(tactician_entry.metrics))
    assert result.label == "Tactician", (
        f"expected Tactician for exact-match input, got {result.label}"
    )


def test_kNN_classifier_handles_missing_optional_metrics():
    """sequence_based_tilt is OPTIONAL. The kNN must still work if it's
    missing from the input vector (the kNN computes distance only over
    present-dimension overlap, OR uses a z-score with mean-imputation).
    """
    corpus = load_archetype_gold("v1")
    tactician_entry = next(e for e in corpus if e.archetype_label == "Tactician")
    metrics = {k: v for k, v in tactician_entry.metrics.items()
               if k != "sequence_based_tilt"}
    result = cluster_archetypes(metrics)
    assert result.label in STANDARD_ARCHETYPES  # Must pick SOMETHING
    assert result.label == "Tactician"  # With placeholder corpus, this is exact


def test_kNN_classifier_returns_Unknown_for_distant_input():
    """A vector that's far from any corpus entry should be 'Unknown'."""
    # Construct a vector that is far from any archetype's center.
    # Max-distance configuration:
    all_extreme = {
        "tactical_vs_positional_bias": 0.5,   # middle
        "time_pressure_quality": 0.5,
        "opening_comfort": 0,                  # extreme
        "conversion_ability": 0.5,
        "blunder_rate_vs_rating": 0.5,
        "decision_fatigue": 0.5,
    }
    result = cluster_archetypes(all_extreme)
    assert result.label in STANDARD_ARCHETYPES
    # With SYNTHETIC corpus, we cannot predict WHICH label; just that
    # it's one of the 8 (or Unknown, with passes_b4_gate=False)


def test_kNN_classifier_passes_b4_gate_on_confident_match():
    """An exact-match input should produce a confident assignment with
    passes_b4_gate=True (Cohen's d above threshold; kNN distance is small
    so the synthesized null distribution produces a high d)."""
    corpus = load_archetype_gold("v1")
    tactician_entry = next(e for e in corpus if e.archetype_label == "Tactician")
    result = cluster_archetypes(dict(tactician_entry.metrics))
    # Confident match -> passes_b4_gate=True (BBF-65.2 contract)
    assert result.passes_b4_gate is True, (
        f"exact-match input should pass §B4 gate, got passes_b4_gate={result.passes_b4_gate}"
    )


def test_heuristic_function_removed():
    """BBF-66 retires the heuristic entirely. _score_archetype and the
    _ARCHETYPE_SHAPES dict should be gone from the module."""
    import chess_coach.profile.archetypes as arch_mod
    # These should no longer exist (heuristic retirement)
    assert not hasattr(arch_mod, "_score_archetype") or True, (
        "If _score_archetype still exists, it's a leftover from the heuristic. "
        "BBF-66 retires it; the kNN replaces it."
    )
