"""Archetype gold corpus loader (BBF-66).

Mirrors the L-2 gold loader (libs/chess_coach/datasets/l2_gold.py) shape:
- ArchetypeGoldEntry dataclass
- load_archetype_gold(version, base_path=None) -> list[ArchetypeGoldEntry]
- load_archetype_gold_with_metadata(version, base_path=None) -> full dict
- validate_archetype_gold(corpus) -> list[str] of errors

The corpus is the REFERENCE VECTORS for the kNN archetype cluster at
services/chess_coach/profile/archetypes.py. DIFFERENT from the L-2 chess
corpus: L-2 is chess-position data (FEN + eval_deltas); this corpus is
player-metric data (the 6 metric dimensions + archetype_label).

The v1 corpus is a SYNTHETIC PLACEHOLDER (per the post-BBF-65 handoff
directive). Real labelled entries replace placeholders in a future BBF.

Public API:

  load_archetype_gold(version="v1", base_path=None)
    Load the corpus for the given version. Returns a list of
    ArchetypeGoldEntry dataclasses.

  load_archetype_gold_with_metadata(version, base_path=None)
    Same, but returns the full dict (including _metadata).

  validate_archetype_gold(corpus)
    Validate the corpus shape. Returns a list of error strings.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ID pattern: AG-vN-NNNN where vN is the version and NNNN is 4-digit zero-padded.
_ID_PATTERN = re.compile(r"^AG-v\d+-\d{4}$")

# Required metric keys (the 6 dimensions cluster_archetypes consumes).
# Note: sequence_based_tilt is OPTIONAL -- only Tilter uses it.
_REQUIRED_METRICS = (
    "tactical_vs_positional_bias",
    "time_pressure_quality",
    "opening_comfort",
    "conversion_ability",
    "blunder_rate_vs_rating",
    "decision_fatigue",
)
_OPTIONAL_METRICS = ("sequence_based_tilt",)


@dataclass
class ArchetypeGoldEntry:
    """One labelled reference vector for kNN archetype cluster.

    Attributes:
        id: The corpus-local id (AG-v1-NNNN).
        archetype_label: One of STANDARD_ARCHETYPES (e.g. "Tactician").
        metrics: Dict mapping metric name to float value.
    """

    id: str
    archetype_label: str
    metrics: dict = field(default_factory=dict)


def load_archetype_gold(version: str = "v1", base_path=None):
    """Load the corpus for the given version.

    Returns: list[ArchetypeGoldEntry].
    """
    raw = load_archetype_gold_with_metadata(version, base_path)
    return [ArchetypeGoldEntry(**e) for e in raw["entries"]]


def load_archetype_gold_with_metadata(version: str = "v1", base_path=None):
    """Same, but returns the full dict (preserves _metadata)."""
    base = Path(base_path) if base_path is not None else _default_base_path()
    corpus_path = base / version / "corpus.json"
    if not corpus_path.is_file():
        raise FileNotFoundError(
            f"Archetype gold corpus not found at {corpus_path}"
        )
    with open(corpus_path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict) or "entries" not in raw:
        raise ValueError(
            f"Archetype gold corpus at {corpus_path} is missing 'entries' key"
        )
    if raw.get("schema_version") != 1:
        raise ValueError(
            f"Archetype gold corpus at {corpus_path} has schema_version "
            f"{raw.get('schema_version')}, expected 1"
        )
    return raw


def validate_archetype_gold(corpus):
    """Validate the corpus shape. Returns a list of error strings."""
    errors = []
    seen_ids = set()
    for entry in corpus:
        if not _ID_PATTERN.match(entry.id):
            errors.append(f"{entry.id} does not match AG-v<version>-NNNN pattern")
        if entry.id in seen_ids:
            errors.append(f"Duplicate id: {entry.id}")
        seen_ids.add(entry.id)
        for required in _REQUIRED_METRICS:
            if required not in entry.metrics:
                errors.append(f"{entry.id} missing required metric {required}")
    return errors


def _default_base_path():
    """Return the default base path for the archetype gold corpus.

    Default: <repo>/tests/gold/archetypes/ -- parallel to
    tests/gold/L2/ (which is the L-2 chess corpus). Mirrors the
    Option B (versioned separate file) pattern from BBF-63.
    """
    # Resolve from this file's location: libs/chess_coach/datasets/archetype_gold.py
    # -> up 3 to repo root -> tests/gold/archetypes
    here = Path(__file__).resolve()
    repo_root = here.parents[3]  # libs/.. -> chess_coach -> repo root
    return repo_root / "tests" / "gold" / "archetypes"
