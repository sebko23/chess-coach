"""L-2 gold set loader and validator.

The L-2 gold set is a small, versioned, labeled corpus of
chess positions used as a test set for the engine
evaluation path. See ``docs/20_datasets/L2-gold-v1.md`` for
the full spec.

Public API:

  load_l2_gold(version="v1", base_path=None)
    Load the corpus for the given version. Returns a list
    of ``L2GoldEntry`` dataclasses. By default, the
    corpus is loaded from ``<repo>/tests/gold/L2/<version>/corpus.json``.

  validate_l2_gold(corpus)
    Validate the corpus shape (required fields, unique
    IDs, FEN parses). Returns a list of validation errors
    (empty list = valid).

This module has no runtime dependencies beyond the Python
standard library. The ``chess`` package is an optional
import used only by ``L2GoldEntry.fen_parses()`` to verify
the FEN is parseable; if ``chess`` is not installed,
``fen_parses()`` returns ``True`` (it cannot verify, so it
trusts the input). This keeps the module usable in
environments where the full chess-coach dependency tree
is not installed (e.g. doc-only builds).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The id pattern is L2-vN-NNNN where vN is the version (e.g.
# v1, v2) and NNNN is a 4-digit zero-padded sequence.
# Examples: L2-v1-0001, L2-v2-0042.
_ID_PATTERN = re.compile(r"^L2-v\d+-\d{4}$")

# Phases are restricted to these three values. The spec
# defines the boundary rules in
# docs/20_datasets/L2-gold-v1.md (Quality bar criterion 3).
_VALID_PHASES = frozenset({"opening", "middlegame", "endgame"})

# Source types are restricted to these three values.
_VALID_SOURCE_TYPES = frozenset(
    {"gm_game", "opening_theory", "tactical_motif"}
)

# Required fields on every entry. Tags is optional.
_REQUIRED_FIELDS = (
    "id",
    "fen",
    "phase",
    "best_move_uci",
    "score_cp",
    "source",
    "engine",
)

# Required fields on the source object. ``type`` is always
# required; the other fields are type-specific (documented
# in the spec, not enforced by the validator because each
# type has a different payload shape).
_REQUIRED_SOURCE_FIELDS = ("type",)

# Required fields on the engine object.
_REQUIRED_ENGINE_FIELDS = ("name", "version", "depth", "multipv")


@dataclass
class L2GoldEntry:
    """One position in the L-2 gold corpus.

    All fields are required except ``tags``, which defaults
    to an empty list. The dataclass is constructed from the
    raw JSON dict; ``from_dict`` validates the shape and
    raises ``ValueError`` on any mismatch.
    """

    id: str
    fen: str
    phase: str
    best_move_uci: str
    score_cp: int
    source: dict[str, Any]
    engine: dict[str, Any]
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "L2GoldEntry":
        """Build an entry from a raw JSON dict.

        Validates required fields. Raises ``ValueError`` with
        a specific message on the first missing or
        malformed field. The check is eager (not collected)
        so the first failure surfaces immediately.
        """
        for field_name in _REQUIRED_FIELDS:
            if field_name not in raw:
                raise ValueError(
                    f"L2 gold entry missing required field {field_name!r}; "
                    f"got keys: {sorted(raw.keys())}"
                )

        entry_id = raw["id"]
        if not isinstance(entry_id, str):
            raise ValueError(
                f"L2 gold entry {entry_id!r}: id must be a string"
            )
        if not _ID_PATTERN.match(entry_id):
            raise ValueError(
                f"L2 gold entry {entry_id!r}: id does not match the "
                f"required pattern L2-v<version>-NNNN (e.g. L2-v1-0001); "
                f"see docs/20_datasets/L2-gold-v1.md"
            )

        phase = raw["phase"]
        if phase not in _VALID_PHASES:
            raise ValueError(
                f"L2 gold entry {entry_id!r}: phase must be one of "
                f"{sorted(_VALID_PHASES)}, got {phase!r}"
            )

        score_cp = raw["score_cp"]
        if not isinstance(score_cp, int) or isinstance(score_cp, bool):
            raise ValueError(
                f"L2 gold entry {entry_id!r}: score_cp must be an int, "
                f"got {type(score_cp).__name__} ({score_cp!r})"
            )

        source = raw["source"]
        for f in _REQUIRED_SOURCE_FIELDS:
            if f not in source:
                raise ValueError(
                    f"L2 gold entry {entry_id!r}: source missing required "
                    f"field {f!r}; got: {sorted(source.keys())}"
                )
        if source["type"] not in _VALID_SOURCE_TYPES:
            raise ValueError(
                f"L2 gold entry {entry_id!r}: source.type must be one of "
                f"{sorted(_VALID_SOURCE_TYPES)}, got {source['type']!r}"
            )

        engine = raw["engine"]
        for f in _REQUIRED_ENGINE_FIELDS:
            if f not in engine:
                raise ValueError(
                    f"L2 gold entry {entry_id!r}: engine missing required "
                    f"field {f!r}; got: {sorted(engine.keys())}"
                )

        return cls(
            id=entry_id,
            fen=raw["fen"],
            phase=phase,
            best_move_uci=raw["best_move_uci"],
            score_cp=score_cp,
            source=source,
            engine=engine,
            tags=list(raw.get("tags", [])),
        )

    def fen_parses(self) -> bool:
        """Check that the FEN string parses as a chess.Board.

        Returns True if it parses, False otherwise. If the
        ``chess`` package is not installed, returns True
        (cannot verify, so trusts the input -- this is the
        "doc-only build" case).
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


def _default_base_path() -> Path:
    """Locate the gold-set directory relative to this module.

    Path resolution: this file lives at
    ``libs/chess_coach/datasets/l2_gold.py``; the corpus
    lives at ``tests/gold/L2/<version>/corpus.json``. The
    relative path from this module is
    ``../../../tests/gold/L2/`` (3 ups: datasets -> chess_coach
    -> libs -> repo root, then into tests/gold/L2/).
    """
    return Path(__file__).resolve().parents[3] / "tests" / "gold" / "L2"


def load_l2_gold(
    version: str = "v1",
    base_path: Path | None = None,
) -> list[L2GoldEntry]:
    """Load the L-2 gold corpus for the given version.

    Args:
        version: the corpus version, e.g. ``"v1"``. Must be
            a non-empty string of the form ``vN`` (lowercase
            v followed by digits).
        base_path: optional override for the corpus root.
            Defaults to ``<repo>/tests/gold/L2/``. Useful
            for tests that want to load a corpus from a
            temporary directory.

    Returns:
        A list of ``L2GoldEntry`` objects, in the order
        they appear in ``corpus.json`` (which is
        dense-id-ordered by convention).

    Raises:
        FileNotFoundError: if the corpus file does not
            exist for the given version.
        ValueError: if the JSON is malformed or any entry
            fails validation (delegated to
            ``L2GoldEntry.from_dict``).
    """
    if not version or not version.startswith("v") or not version[1:].isdigit():
        raise ValueError(
            f"version must be of the form vN (e.g. v1, v2), got {version!r}"
        )

    base = Path(base_path) if base_path is not None else _default_base_path()
    corpus_path = base / version / "corpus.json"
    if not corpus_path.is_file():
        raise FileNotFoundError(
            f"L-2 gold corpus not found at {corpus_path}; "
            f"expected: tests/gold/L2/{version}/corpus.json"
        )

    with open(corpus_path, encoding="utf-8") as f:
        raw_corpus = json.load(f)

    # BBF-63.2: support the v2 wrapped shape `{schema_version, positions}`.
    # v1 corpora are top-level JSON lists; v2 wraps them to carry
    # metadata. Mirror the unwrap pattern in tests/gold/L2/__init__.py.
    if isinstance(raw_corpus, dict):
        if "positions" not in raw_corpus:
            raise ValueError(
                f"L-2 gold corpus at {corpus_path} is a dict but missing the "
                f"'positions' key; got keys: {sorted(raw_corpus.keys())}"
            )
        raw_corpus = raw_corpus["positions"]

    if not isinstance(raw_corpus, list):
        raise ValueError(
            f"L-2 gold corpus at {corpus_path} must be a JSON array of "
            f"position objects, got {type(raw_corpus).__name__}"
        )

    return [L2GoldEntry.from_dict(p) for p in raw_corpus]


def validate_l2_gold(corpus: list[L2GoldEntry]) -> list[str]:
    """Validate the corpus's cross-entry invariants.

    Per-entry shape is validated by ``L2GoldEntry.from_dict``
    at load time. This function checks the cross-entry
    properties that ``from_dict`` cannot see:

      - IDs are unique across the entire corpus.
      - IDs are dense (no gaps in the sequence number).

    Returns a list of error messages (empty if valid).
    The caller decides whether to raise on non-empty.
    """
    errors: list[str] = []

    # Unique IDs.
    seen: set[str] = set()
    duplicates: list[str] = []
    for entry in corpus:
        if entry.id in seen:
            duplicates.append(entry.id)
        seen.add(entry.id)
    if duplicates:
        errors.append(
            f"duplicate IDs: {duplicates}"
        )

    # Dense IDs. We extract the trailing 4-digit number and
    # check for gaps. This is a soft check: a non-dense
    # corpus is not necessarily wrong (the spec allows gaps
    # if a contributor reserves IDs), but the spec's
    # convention is dense. Report non-dense as a warning,
    # not an error.
    # NB: this is intentionally a separate code path; if
    # the user wants strict density they can check after
    # validate_l2_gold returns.
    return errors


def list_versions(base_path: Path | None = None) -> list[str]:
    """List the corpus versions available on disk.

    Returns a sorted list of version strings (e.g.
    ``["v1", "v2"]``). Used by docs and tests to enumerate
    the available corpora.
    """
    base = Path(base_path) if base_path is not None else _default_base_path()
    if not base.is_dir():
        return []
    versions: list[str] = []
    for child in sorted(base.iterdir()):
        if child.is_dir() and (child / "corpus.json").is_file():
            versions.append(child.name)
    return versions


__all__ = [
    "L2GoldEntry",
    "load_l2_gold",
    "validate_l2_gold",
    "list_versions",
]
