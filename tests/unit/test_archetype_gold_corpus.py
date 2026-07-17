"""Tests for BBF-66 archetype-gold corpus loader (mirrors test_l2_gold_dataset.py)."""
import pytest
from pathlib import Path
import json

# 1. Loader returns list[ArchetypeGoldEntry] from the v1 corpus.
def test_v1_corpus_loads_as_list():
    from chess_coach.datasets.archetype_gold import load_archetype_gold
    corpus = load_archetype_gold("v1")
    assert isinstance(corpus, list)
    assert len(corpus) >= 14  # 2 per archetype x 7 = 14

# 2. Each entry has the required fields (id, archetype_label, metrics).
def test_entries_have_required_fields():
    from chess_coach.datasets.archetype_gold import load_archetype_gold
    corpus = load_archetype_gold("v1")
    required_metrics = {"tactical_vs_positional_bias", "time_pressure_quality",
                        "opening_comfort", "conversion_ability",
                        "blunder_rate_vs_rating", "decision_fatigue"}
    for entry in corpus:
        assert entry.id.startswith("AG-v1-")
        for m in required_metrics:
            assert m in entry.metrics, f"{entry.id} missing metric {m}"

# 3. archetype_label is one of STANDARD_ARCHETYPES (8 values).
def test_archetype_labels_are_standard():
    from chess_coach.datasets.archetype_gold import load_archetype_gold
    from chess_coach.profile import STANDARD_ARCHETYPES
    corpus = load_archetype_gold("v1")
    for entry in corpus:
        assert entry.archetype_label in STANDARD_ARCHETYPES

# 4. _metadata.WARNING exists and contains SYNTHETIC.
def test_metadata_warning_exists():
    from chess_coach.datasets.archetype_gold import load_archetype_gold_with_metadata
    result = load_archetype_gold_with_metadata("v1")
    assert "WARNING" in result["_metadata"]
    assert "SYNTHETIC" in result["_metadata"]["WARNING"]

# 5. Unknown version raises (not FileNotFoundError or KeyError per the
#    arch_gold pattern; choose the most specific).
def test_load_unknown_version_raises():
    from chess_coach.datasets.archetype_gold import load_archetype_gold
    with pytest.raises((ValueError, FileNotFoundError, KeyError)):
        load_archetype_gold("v999")
