"""Narrative gold corpus loader (BBF-69.1).

The narrative gold corpus is the set of well-explained chess positions
that ground the LLM narration output. Each entry pairs a FEN with a
50-200 word coaching paragraph explaining WHY the position is
good/bad/complex, sourced from a real chess book or GM analysis.

Mirrors the shape of the existing gold loaders
(libs/chess_coach/datasets/l2_gold.py for engine eval gold,
libs/chess_coach/datasets/archetype_gold.py for archetype cluster
gold) so future BBFs that consume narrative gold can use the same
loader idioms.

The v1 corpus is a SYNTHETIC PLACEHOLDER (per the post-BBF-65
handoff directive and the BBF-69 plan in
docs/16_audit/BBF-68.1-candidate-survey-2026-07-17.md §"Narrative
grounding corpus"). Real hand-curated entries with provenance
citations from chess books (Logical Chess Move by Move,
Reassessing Your Chess, etc.) replace placeholders in BBF-69.2
(domain-expert work, not the agent's).

Public API:

  load_narrative_gold(version="v1", base_path=None)
    Load the corpus for the given version. Returns a list
    of NarrativeGoldEntry dataclasses.

  load_narrative_gold_with_metadata(version="v1", base_path=None)
    Same, but returns the full dict (including _metadata and
    schema_version). Useful for tooling that wants to surface
    corpus provenance.

  validate_narrative_gold(corpus)
    Validate the corpus shape. Returns a list of error strings
    (empty list = valid).

This module has no runtime dependencies beyond the Python standard
library. The ``chess`` package is an optional import used only by
NarrativeGoldEntry.fen_parses() to verify the FEN is parseable; if
``chess`` is not installed, fen_parses() returns True (it cannot
verify, so it trusts the input). This keeps the module usable in
environments where the full chess-coach dependency tree is not
installed (e.g. doc-only builds).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ID pattern: NG-vN-NNNN where vN is the version (e.g. v1) and NNNN
# is a 4-digit zero-padded sequence. Examples: NG-v1-0001, NG-v1-0023.
_ID_PATTERN = re.compile(r"^NG-v\d+-\d{4}$")

# Version pattern for the corpus version argument: lowercase 'v'
# followed by one or more digits. Examples: 'v1', 'v2', 'v42'.
_VERSION_PATTERN = re.compile(r"^v\d+$")

# Minimum length for narrative_explanation (50 chars). The BBF-69 plan
# calls for 50-200 word paragraphs (~300-1200 chars); 50 is the floor
# below which an entry is almost certainly accidental (typo, stub).
_MIN_NARRATIVE_CHARS = 50

# Source object required fields. `type` is always required; the
# other fields are type-specific (book/GM_game/online_article) and
# are documented in the spec at docs/16_audit/BBF-68.1-candidate-survey-
# 2026-07-17.md, not enforced by the validator because each type has
# a different payload shape.
_REQUIRED_SOURCE_FIELDS = ("type",)


@dataclass
class NarrativeGoldEntry:
    """One position with a hand-curated coaching narrative.

    Attributes:
        id: The corpus-local id (NG-v<version>-NNNN).
        fen: A parseable chess position in standard FEN.
        narrative_explanation: 50-200 word coaching paragraph
            explaining WHY the position is good/bad/complex.
            The narration pipeline should cite this paragraph as
            the grounding source for any LLM output about this
            position.
        source: Provenance dict with at least a `type` key.
            Type-specific fields: e.g. for type=book, the source
            object carries `title`, `author`, `chapter`, `page`.
            See the BBF-69 spec for the full schema.
        tags: Optional list of free-form tags (e.g. "opening",
            "tactical", "endgame"). Used by BBF-69.3 for nearest-
            neighbour lookup filtering.
    """

    id: str
    fen: str
    narrative_explanation: str
    source: dict[str, Any]
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> NarrativeGoldEntry:
        """Build an entry from a raw JSON dict.

        Validates required fields. Raises ValueError with a
        specific message on the first missing or malformed
        field. The check is eager (not collected) so the first
        failure surfaces immediately.
        """
        for field_name in ("id", "fen", "narrative_explanation", "source"):
            if field_name not in raw:
                raise ValueError(
                    f"Narrative gold entry missing required field "
                    f"{field_name!r}; got keys: {sorted(raw.keys())}"
                )

        entry_id = raw["id"]
        if not isinstance(entry_id, str):
            raise ValueError(
                f"Narrative gold entry {entry_id!r}: id must be a string"
            )
        if not _ID_PATTERN.match(entry_id):
            raise ValueError(
                f"Narrative gold entry {entry_id!r}: id does not match the "
                f"required pattern NG-v<version>-NNNN (e.g. NG-v1-0001)"
            )

        fen = raw["fen"]
        if not isinstance(fen, str):
            raise ValueError(
                f"Narrative gold entry {entry_id!r}: fen must be a string"
            )

        narrative = raw["narrative_explanation"]
        if not isinstance(narrative, str):
            raise ValueError(
                f"Narrative gold entry {entry_id!r}: "
                f"narrative_explanation must be a string"
            )
        if len(narrative) < _MIN_NARRATIVE_CHARS:
            raise ValueError(
                f"Narrative gold entry {entry_id!r}: "
                f"narrative_explanation too short "
                f"({len(narrative)} chars < {_MIN_NARRATIVE_CHARS}); "
                f"this is almost certainly accidental"
            )

        source = raw["source"]
        if not isinstance(source, dict):
            raise ValueError(
                f"Narrative gold entry {entry_id!r}: "
                f"source must be a dict, got {type(source).__name__}"
            )
        for f in _REQUIRED_SOURCE_FIELDS:
            if f not in source:
                raise ValueError(
                    f"Narrative gold entry {entry_id!r}: "
                    f"source missing required field {f!r}; "
                    f"got: {sorted(source.keys())}"
                )

        return cls(
            id=entry_id,
            fen=fen,
            narrative_explanation=narrative,
            source=source,
            tags=list(raw.get("tags", [])),
        )

    def fen_parses(self) -> bool:
        """Check that the FEN string parses as a chess.Board.

        Returns True if it parses, False otherwise. If the
        ``chess`` package is not installed, returns True (cannot
        verify, so trusts the input -- this is the "doc-only
        build" case).
        """
        try:
            import chess  # type: ignore[import-not-found]
        except ImportError:
            return True
        try:
            chess.Board(self.fen)
        except (ValueError, AssertionError):
            return False
        return True


def load_narrative_gold(
    version: str = "v1",
    base_path: Path | None = None,
) -> list[NarrativeGoldEntry]:
    """Load the narrative gold corpus for the given version.

    Args:
        version: the corpus version, e.g. "v1". Must be a
            non-empty string of the form vN (lowercase v
            followed by digits).
        base_path: optional override for the corpus root.
            Defaults to <repo>/tests/gold/narrative/. Useful
            for tests that want to load a corpus from a
            temporary directory.

    Returns:
        A list of NarrativeGoldEntry objects, in the order
        they appear in corpus.json (which is dense-id-ordered
        by convention).

    Raises:
        FileNotFoundError: if the corpus file does not exist
            for the given version.
        ValueError: if the JSON is malformed or any entry fails
            validation (delegated to NarrativeGoldEntry.from_dict).
    """
    if not isinstance(version, str) or not _VERSION_PATTERN.match(version):
        raise ValueError(
            f"version must be a string of the form 'vN' (e.g. 'v1'), "
            f"got: {version!r}"
        )

    raw = load_narrative_gold_with_metadata(version, base_path)
    return [NarrativeGoldEntry.from_dict(e) for e in raw["entries"]]


def load_narrative_gold_with_metadata(
    version: str = "v1",
    base_path: Path | None = None,
) -> dict[str, Any]:
    """Same, but returns the full dict (preserves _metadata and
    schema_version).

    The returned dict has at minimum:
      - "schema_version": int (currently always 1)
      - "entries": list of raw entry dicts (callers wanting parsed
        NarrativeGoldEntry objects should use load_narrative_gold())
      - "_metadata": optional dict with corpus provenance + warnings
        (SYNTHETIC PLACEHOLDER corpora use _metadata.WARNING).

    Useful for tooling that wants to surface corpus provenance
    (e.g. "this corpus is a SYNTHETIC PLACEHOLDER for BBF-69.1;
    real entries ship in BBF-69.2").
    """
    # Validate version BEFORE Path() construction so a None or
    # malformed version produces a clean ValueError instead of a
    # TypeError from Path(None).
    if not isinstance(version, str) or not _VERSION_PATTERN.match(version):
        raise ValueError(
            f"version must be a string of the form 'vN' (e.g. 'v1'), "
            f"got: {version!r}"
        )
    base = Path(base_path) if base_path is not None else _default_base_path()
    corpus_path = base / version / "corpus.json"
    if not corpus_path.is_file():
        raise FileNotFoundError(
            f"Narrative gold corpus not found at {corpus_path}; "
            f"expected: tests/gold/narrative/{version}/corpus.json"
        )

    with open(corpus_path, encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError(
            f"Narrative gold corpus at {corpus_path} must be a JSON "
            f"object with 'entries' and 'schema_version' keys; "
            f"got {type(raw).__name__}"
        )
    if "entries" not in raw:
        raise ValueError(
            f"Narrative gold corpus at {corpus_path} is missing "
            f"the 'entries' key; got keys: {sorted(raw.keys())}"
        )
    if raw.get("schema_version") != 1:
        raise ValueError(
            f"Narrative gold corpus at {corpus_path} has "
            f"schema_version {raw.get('schema_version')}, expected 1"
        )
    return raw


def validate_narrative_gold(
    corpus: list[NarrativeGoldEntry],
) -> list[str]:
    """Validate the corpus's cross-entry invariants.

    Per-entry shape is validated by NarrativeGoldEntry.from_dict at
    load time. This function checks the cross-entry properties
    that from_dict cannot see:

      - IDs are unique across the entire corpus.
      - FENs are unique across the corpus (a given position
        should appear once; duplicate FENs would be ambiguous
        when the narration pipeline looks up the closest match).

    Returns a list of error messages (empty if valid). The
    caller decides whether to raise on non-empty.
    """
    errors: list[str] = []

    seen_ids: set[str] = set()
    duplicates_id: list[str] = []
    for entry in corpus:
        if entry.id in seen_ids:
            duplicates_id.append(entry.id)
        seen_ids.add(entry.id)
    if duplicates_id:
        errors.append(f"duplicate IDs: {duplicates_id}")

    seen_fens: set[str] = set()
    duplicates_fen: list[str] = []
    for entry in corpus:
        if entry.fen in seen_fens:
            duplicates_fen.append(entry.id)
        seen_fens.add(entry.fen)
    if duplicates_fen:
        errors.append(
            f"duplicate FENs at: {duplicates_fen}"
        )

    return errors


def list_versions(base_path: Path | None = None) -> list[str]:
    """List the corpus versions available on disk.

    Returns a sorted list of version strings (e.g. ["v1", "v2"]).
    Used by docs and tests to enumerate the available corpora.
    """
    base = Path(base_path) if base_path is not None else _default_base_path()
    if not base.is_dir():
        return []
    versions: list[str] = []
    for child in sorted(base.iterdir()):
        if child.is_dir() and (child / "corpus.json").is_file():
            versions.append(child.name)
    return versions


def _default_base_path() -> Path:
    """Locate the gold-set directory relative to this module.

    Path resolution: this file lives at
    libs/chess_coach/datasets/narrative_gold.py; the corpus lives
    at tests/gold/narrative/<version>/corpus.json. The relative
    path from this module is ../../../tests/gold/narrative/
    (3 ups: datasets -> chess_coach -> libs -> repo root, then
    into tests/gold/narrative/).
    """
    return Path(__file__).resolve().parents[3] / "tests" / "gold" / "narrative"


__all__ = [
    "NarrativeGoldEntry",
    "load_narrative_gold",
    "load_narrative_gold_with_metadata",
    "validate_narrative_gold",
    "list_versions",
]
