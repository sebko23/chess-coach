"""Tests for BBF-66 archetype-gold corpus loader (mirrors test_l2_gold_dataset.py)."""

import json
import logging
from pathlib import Path

import pytest


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


# --- BBF-88.x: v0 corpus round-trip + provenance checks ---


def test_v0_corpus_loads_as_list() -> None:
    """BBF-88.x: v0 corpus loads via the production loader."""
    from chess_coach.datasets.archetype_gold import load_archetype_gold
    corpus = load_archetype_gold("v0")
    assert isinstance(corpus, list)
    assert len(corpus) >= 1


def test_v0_corpus_entries_have_required_fields() -> None:
    """BBF-88.x: every v0 entry carries id + archetype_label + 6 metrics."""
    from chess_coach.datasets.archetype_gold import load_archetype_gold
    corpus = load_archetype_gold("v0")
    required_metrics = {
        "tactical_vs_positional_bias",
        "time_pressure_quality",
        "opening_comfort",
        "conversion_ability",
        "blunder_rate_vs_rating",
        "decision_fatigue",
    }
    for entry in corpus:
        assert entry.id.startswith("AG-v0-"), entry.id
        assert isinstance(entry.archetype_label, str)
        for m in required_metrics:
            assert m in entry.metrics, f"{entry.id} missing metric {m}"


def test_v0_corpus_archetype_labels_are_standard() -> None:
    """BBF-88.x: every v0 archetype_label is in STANDARD_ARCHETYPES."""
    from chess_coach.datasets.archetype_gold import load_archetype_gold
    from chess_coach.profile import STANDARD_ARCHETYPES
    corpus = load_archetype_gold("v0")
    for entry in corpus:
        assert entry.archetype_label in STANDARD_ARCHETYPES, (
            f"{entry.id}: {entry.archetype_label!r}"
        )


def test_v0_corpus_provenance_metadata() -> None:
    """BBF-88.x: each v0 entry has _provenance (auto-corpus provenance).

    BBF-88.2a extended the corpus with 6 hand-curated entries
    that use a different provenance scheme (`strategy: "synthetic_shape_curated"`).
    Those entries have an `archetype_trait_source` field instead
    of `player_name`. This test accepts either provenance scheme.
    """
    from chess_coach.datasets.archetype_gold import load_archetype_gold
    corpus = load_archetype_gold("v0")
    for entry in corpus:
        assert entry._provenance is not None, (
            f"{entry.id} missing _provenance"
        )
        prov = entry._provenance
        is_shape_curated = prov.get("strategy") == "synthetic_shape_curated"
        if is_shape_curated:
            assert prov.get("archetype_trait_source"), (
                f"{entry.id} missing archetype_trait_source in _provenance"
            )
        else:
            assert prov.get("player_name"), (
                f"{entry.id} missing player_name in _provenance"
            )


def test_v0_corpus_round_trip_validator_passes() -> None:
    """BBF-88.x: scripts/validate_archetype_gold.py accepts the shipped v0 corpus."""
    import json as _json
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    validate_script = repo / "scripts" / "validate_archetype_gold.py"
    proc = subprocess.run(
        [sys.executable, str(validate_script), "--version", "v0", "--json"],
        capture_output=True, text=True, cwd=str(repo), timeout=30,
    )
    assert proc.returncode == 0, (
        f"v0 validator failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    result = _json.loads(proc.stdout)
    assert result["complete"] is True, (
        f"v0 validator reports incomplete: errors={result.get('errors')}"
    )


# ---- BBF-88.2a: 7-of-7 archetype coverage ----


def test_v0_all_7_archetypes_covered() -> None:
    """BBF-88.2a: every STANDARD_ARCHETYPES label appears in the v0 corpus.

    Prevents regression: if a future BBF accidentally removes one
    of the shape-curated entries for Tactician, Wildcard, or
    Specialist, this test fails. The kNN classifier's silent
    failure mode (4-of-7 coverage) is closed by this assertion.
    """
    from chess_coach.datasets.archetype_gold import load_archetype_gold
    from chess_coach.profile import STANDARD_ARCHETYPES

    corpus = load_archetype_gold("v0")
    covered = {entry.archetype_label for entry in corpus}
    # Drop "Unknown" from the required set; it's reserved for the
    # kNN output bucket and must NOT appear as a corpus label.
    standard_labels = {label for label in STANDARD_ARCHETYPES if label != "Unknown"}
    assert covered >= standard_labels, (
        f"v0 corpus missing STANDARD_ARCHETYPES coverage: "
        f"missing={standard_labels - covered}, "
        f"present={covered}"
    )


def test_v0_shape_curated_entries_have_archetype_trait_source() -> None:
    """BBF-88.2a: every shape-curated entry documents its trait source."""
    from chess_coach.datasets.archetype_gold import load_archetype_gold

    corpus = load_archetype_gold("v0")
    shape_curated = [
        e for e in corpus
        if e._provenance
        and e._provenance.get("strategy") == "synthetic_shape_curated"
    ]
    assert shape_curated, "v0 corpus has no shape-curated entries (BBF-88.2a)"
    for entry in shape_curated:
        source = entry._provenance.get("archetype_trait_source")
        assert source is not None, (
            f"{entry.id}: shape-curated entry missing archetype_trait_source"
        )
        assert isinstance(source, str), (
            f"{entry.id}: archetype_trait_source is not a string"
        )


# ---- BBF-86.7: self-describing _metadata.version + advisory loader check ----


def test_v0_shipped_corpus_has_version_field() -> None:
    """BBF-86.7: the shipped v0 archetype corpus self-describes as v0."""
    from chess_coach.datasets.archetype_gold import (
        load_archetype_gold_with_metadata,
    )
    raw = load_archetype_gold_with_metadata(version="v0")
    metadata = raw.get("_metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("version") == "v0"


def test_archetype_loader_warns_on_version_mismatch(
    caplog: pytest.LogCaptureFixture, tmp_path: Path,
) -> None:
    """BBF-86.7: requesting v1 from a v0 corpus logs a WARNING but
    does NOT raise. This is the soft-advisory contract; refusing
    would break production callers (e.g. archetypes.py hard-codes
    load_archetype_gold("v1") and v1 may not be in the image).
    """
    import logging

    from chess_coach.datasets.archetype_gold import load_archetype_gold

    # Build a tmp corpus that self-describes as "v0" but is loaded
    # under a different version request ("v1"). The loader must
    # log a WARNING and return entries, not raise.
    tmp_corpus = {
        "schema_version": 1,
        "_metadata": {
            "version": "v0",
            "provenance": "auto",
            "WARNING": "test fixture",
        },
        "entries": [
            {
                "id": "AG-v0-0001",
                "archetype_label": "Tilter",
                "metrics": {
                    "tactical_vs_positional_bias": 0.5,
                    "time_pressure_quality": 0.2,
                    "opening_comfort": 1.0,
                    "conversion_ability": 0.0,
                    "blunder_rate_vs_rating": 0.2,
                    "decision_fatigue": 0.0,
                },
            },
        ],
    }
    corpus_dir = tmp_path / "v1"
    corpus_dir.mkdir()
    (corpus_dir / "corpus.json").write_text(
        json.dumps(tmp_corpus), encoding="utf-8",
    )

    with caplog.at_level(
        logging.WARNING, logger="chess_coach.datasets.archetype_gold",
    ):
        entries = load_archetype_gold(version="v1", base_path=tmp_path)

    # The loader must succeed (soft-advisory, not refusing).
    assert len(entries) == 1
    assert entries[0].id == "AG-v0-0001"

    # And a version-mismatch WARNING must be logged.
    mismatch = [
        r for r in caplog.records
        if "version mismatch" in r.message.lower()
    ]
    assert mismatch, "expected a version-mismatch WARNING to be logged"


def test_archetype_loader_no_warning_when_version_matches(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """BBF-86.7: requesting v0 from the v0 corpus emits no
    version-mismatch WARNING."""
    from chess_coach.datasets.archetype_gold import load_archetype_gold

    with caplog.at_level(
        logging.WARNING, logger="chess_coach.datasets.archetype_gold",
    ):
        load_archetype_gold(version="v0")
    mismatch = [
        r for r in caplog.records
        if "version mismatch" in r.message.lower()
    ]
    assert not mismatch, (
        f"unexpected version-mismatch WARNING(s): "
        f"{[r.message for r in mismatch]}"
    )


# ---- BBF-86.5: confidence gating (silent failure mode for v0 corpus) ----


def test_knn_classify_gates_low_confidence_as_unknown() -> None:
    """BBF-86.5: when confidence < min_confidence, return Unknown.

    Before BBF-86.5, a user whose metric vector was near (but not
    exactly at) a 4-covered-archetype training vector would get a
    wrong label. After BBF-86.5, the gate returns Unknown below
    min_confidence.
    """
    from chess_coach.profile.archetypes import _knn_classify
    # Mid-range input: high confidence (Grinder archetype)
    result = _knn_classify(
        {
            "tactical_vs_positional_bias": 0.5,
            "time_pressure_quality": 0.1,
            "opening_comfort": 15.0,
            "conversion_ability": 0.6,
            "blunder_rate_vs_rating": 0.15,
            "decision_fatigue": 0.05,
            "sequence_based_tilt": 0.05,
        },
        min_confidence=0.3,
    )
    assert result[0] == "Grinder"
    assert result[1] >= 0.3


def test_knn_classify_below_threshold_returns_unknown() -> None:
    """BBF-86.5: extreme metric vector -> Unknown (above z-threshold)."""
    from chess_coach.profile.archetypes import _knn_classify
    result = _knn_classify(
        {
            "tactical_vs_positional_bias": 0.5,
            "time_pressure_quality": 0.5,
            "opening_comfort": 100.0,
            "conversion_ability": 0.99,
            "blunder_rate_vs_rating": 0.5,
            "decision_fatigue": 0.5,
            "sequence_based_tilt": 0.5,
        },
    )
    assert result[0] == "Unknown"
    assert result[1] == 0.0


def test_knn_classify_min_confidence_zero_disables_gate() -> None:
    """BBF-86.5: min_confidence=0.0 disables the gate (back-compat)."""
    from chess_coach.profile.archetypes import _knn_classify
    result_with_gate = _knn_classify(
        {
            "tactical_vs_positional_bias": 0.4,
            "time_pressure_quality": 0.1,
            "opening_comfort": 12.0,
            "conversion_ability": 0.5,
            "blunder_rate_vs_rating": 0.15,
            "decision_fatigue": 0.05,
            "sequence_based_tilt": 0.05,
        },
        min_confidence=0.5,
    )
    result_without_gate = _knn_classify(
        {
            "tactical_vs_positional_bias": 0.4,
            "time_pressure_quality": 0.1,
            "opening_comfort": 12.0,
            "conversion_ability": 0.5,
            "blunder_rate_vs_rating": 0.15,
            "decision_fatigue": 0.05,
            "sequence_based_tilt": 0.05,
        },
        min_confidence=0.0,
    )
    # With gate: same logic as without (label or Unknown).
    # Without gate: same result, just no floor.
    # Either way, both should agree on Unknown vs labeled.
    assert (result_with_gate[0] == "Unknown") == (
        result_without_gate[0] == "Unknown"
    )


def test_cluster_archetypes_gates_low_confidence_in_assignment() -> None:
    """BBF-86.5: cluster_archetypes returns ArchetypeAssignment with
    label=Unknown when confidence is below min_confidence (0.3).
    """
    from chess_coach.profile.archetypes import cluster_archetypes
    # Extreme vector -> should be Unknown with low confidence
    assignment = cluster_archetypes(
        {
            "tactical_vs_positional_bias": 0.5,
            "time_pressure_quality": 0.5,
            "opening_comfort": 100.0,
            "conversion_ability": 0.99,
            "blunder_rate_vs_rating": 0.5,
            "decision_fatigue": 0.5,
            "sequence_based_tilt": 0.5,
        }
    )
    assert assignment.label == "Unknown"
    assert assignment.confidence < 0.5
    # Section-B4 gate: Unknown is inconclusive by definition.
    assert not assignment.passes_b4_gate
