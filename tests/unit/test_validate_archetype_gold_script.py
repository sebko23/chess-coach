"""Unit tests for the BBF-75 archetype-gold completion validator."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.validate_archetype_gold import validate_completion

_LABELS = (
    "Tactician",
    "Positional Player",
    "Grinder",
    "Wildcard",
    "Specialist",
    "Tilter",
    "Endgame Specialist",
)


def _valid_entry(id: str, label: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": id,
        "archetype_label": label,
        "metrics": {
            "tactical_vs_positional_bias": 0.50,
            "time_pressure_quality": 0.10,
            "opening_comfort": 20,
            "conversion_ability": 0.60,
            "blunder_rate_vs_rating": 0.15,
            "decision_fatigue": 0.05,
            "sequence_based_tilt": 0.05,
        },
    }
    for key, value in overrides.items():
        base[key] = value
    return base


def _complete_corpus() -> dict[str, object]:
    """Build a 28-entry completion-ready corpus with >= 2 per non-Unknown label."""
    entries: list[dict[str, object]] = []
    plan: list[tuple[str, int]] = [
        ("Tactician", 4),
        ("Positional Player", 4),
        ("Grinder", 4),
        ("Wildcard", 4),
        ("Specialist", 4),
        ("Tilter", 4),
        ("Endgame Specialist", 4),
    ]
    counter = 1
    for label, count in plan:
        for _ in range(count):
            entries.append(_valid_entry(f"AG-v1-{counter:04d}", label))
            counter += 1
    return {
        "schema_version": 1,
        "_metadata": {"curated_by": "test fixture"},
        "entries": entries,
    }


def _write_corpus(tmp_path: Path, corpus: dict[str, object]) -> Path:
    base = tmp_path / "archetypes"
    version_dir = base / "v1"
    version_dir.mkdir(parents=True)
    (version_dir / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    return base


def test_complete_corpus_passes(tmp_path: Path) -> None:
    base = _write_corpus(tmp_path, _complete_corpus())
    assert validate_completion(base_path=base) == []


def test_shipped_placeholder_corpus_fails_completion_gate() -> None:
    """The shipped 14-entry placeholder must fail the strict validator.

    Three reasons: corpus size below 20, _metadata.WARNING present, and
    placeholder-marker text embedded in the corpus body.
    """
    errors = validate_completion()
    assert any("expected 20-40 entries" in error for error in errors)
    assert any("_metadata.WARNING" in error for error in errors)
    assert any("placeholder marker remains" in error for error in errors)


def test_missing_required_metric_is_reported(tmp_path: Path) -> None:
    corpus = _complete_corpus()
    entries = corpus["entries"]
    assert isinstance(entries, list)
    del entries[0]["metrics"]["time_pressure_quality"]  # type: ignore[attr-defined]
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert any("missing required metric 'time_pressure_quality'" in error for error in errors)


def test_non_numeric_metric_is_reported(tmp_path: Path) -> None:
    corpus = _complete_corpus()
    entries = corpus["entries"]
    assert isinstance(entries, list)
    entries[0]["metrics"]["decision_fatigue"] = "low"  # type: ignore[index]
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert any("'decision_fatigue' is not numeric" in error for error in errors)


def test_sparse_ids_are_reported(tmp_path: Path) -> None:
    corpus = _complete_corpus()
    entries = corpus["entries"]
    assert isinstance(entries, list)
    entries[-1]["id"] = "AG-v1-0030"  # gap at the end
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert any("IDs must be dense and ordered" in error for error in errors)


def test_below_minimum_per_label_is_reported(tmp_path: Path) -> None:
    """If one of the non-Unknown labels has fewer than 2 entries, the gate fails.

    A 28-entry corpus with 4 Tilters and 4 Tacticians but only 1
    Endgame Specialist must report the per-label minimum for Endgame
    Specialist (and the total size still passes).
    """
    corpus = _complete_corpus()
    entries = corpus["entries"]
    assert isinstance(entries, list)
    # Drop the second Endgame Specialist entry (keep only AG-v1-0027).
    filtered = [e for e in entries if e["archetype_label"] != "Endgame Specialist"]
    filtered.append(_valid_entry("AG-v1-0027", "Endgame Specialist"))
    corpus["entries"] = filtered
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert any(
        "found 1 for 'Endgame Specialist'" in error for error in errors
    )


def test_placeholder_marker_is_recursive(tmp_path: Path) -> None:
    """A 'STUB' hidden inside one entry's metrics dict must still be detected."""
    corpus = copy.deepcopy(_complete_corpus())
    entries = corpus["entries"]
    assert isinstance(entries, list)
    entries[0]["archetype_label"] = "STUB Tactician"  # type: ignore[index]
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert any("placeholder marker remains" in error for error in errors)


def test_above_maximum_size_is_reported(tmp_path: Path) -> None:
    """A 41-entry corpus must be rejected as too large."""
    corpus = _complete_corpus()
    entries = corpus["entries"]
    assert isinstance(entries, list)
    # Append extra entries past the maximum.
    for index in range(len(entries) + 1, len(entries) + 14):
        label = _LABELS[(index - 1) % len(_LABELS)]
        entries.append(_valid_entry(f"AG-v1-{index:04d}", label))
    corpus["entries"] = entries
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert any("expected 20-40 entries, found 41" in error for error in errors)


def test_unknown_label_in_corpus_is_rejected(tmp_path: Path) -> None:
    """`Unknown` is reserved for kNN outputs; it cannot be a corpus label.

    The strict validator reports any entry whose label is not in the
    allowed set (Tactician, Positional Player, Grinder, Wildcard,
    Specialist, Tilter, Endgame Specialist). `Unknown` is the
    kNN output bucket and must never appear in the corpus.
    """
    corpus = _complete_corpus()
    entries = corpus["entries"]
    assert isinstance(entries, list)
    entries[0]["archetype_label"] = "Unknown"  # type: ignore[index]
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert any(
        "is not a corpus label" in error and "'Unknown'" in error
        for error in errors
    )
