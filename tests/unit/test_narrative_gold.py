"""Unit tests for the narrative gold corpus loader (BBF-69.1).

Mirrors the BBF-43 boot test pattern: a self-contained test that
exercises the public API without depending on external state. The
shipped v1 corpus is a SYNTHETIC PLACEHOLDER; the tests use an
in-memory corpus to avoid coupling to that placeholders' content.

A separate test class (`TestShippedCorpus`) verifies that the
shipped v1 placeholder corpus loads cleanly and validates -- this
test catches regressions when the user (BBF-69.2) replaces the
placeholders with real entries.
"""
from __future__ import annotations

import json

import pytest

from chess_coach.datasets.narrative_gold import (
    NarrativeGoldEntry,
    list_versions,
    load_narrative_gold,
    load_narrative_gold_with_metadata,
    validate_narrative_gold,
)


# A minimal valid entry. Each test that needs a variant copies this
# and overrides the field under test. The narrative_explanation
# is intentionally >=50 chars to satisfy the loader's floor.
def _valid_entry(id: str = "NG-v1-0001", **overrides: object) -> dict[str, object]:
    base = {
        "id": id,
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "narrative_explanation": (
            "This is a valid test narrative that satisfies the loader's "
            "minimum-length floor of 50 characters while remaining "
            "clearly placeholder text for unit-test purposes."
        ),
        "source": {
            "type": "book",
            "title": "Test book",
            "author": "Test author",
            "chapter": "Test chapter",
            "page": "1",
        },
        "tags": ["test"],
    }
    base.update(overrides)
    return base


class TestNarrativeGoldEntry:
    def test_from_dict_minimal_valid(self) -> None:
        """A minimal entry with all required fields parses."""
        entry = NarrativeGoldEntry.from_dict(_valid_entry())
        assert entry.id == "NG-v1-0001"
        assert entry.fen == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        assert entry.tags == ["test"]

    def test_from_dict_default_tags(self) -> None:
        """Tags defaults to an empty list when missing."""
        raw = _valid_entry()
        raw.pop("tags")
        entry = NarrativeGoldEntry.from_dict(raw)
        assert entry.tags == []

    def test_from_dict_missing_required_field(self) -> None:
        """Each required field is checked; first missing one raises."""
        for missing_field in ("id", "fen", "narrative_explanation", "source"):
            raw = _valid_entry()
            del raw[missing_field]
            with pytest.raises(
                ValueError, match=f"missing required field {missing_field!r}"
            ):
                NarrativeGoldEntry.from_dict(raw)

    def test_from_dict_id_must_match_pattern(self) -> None:
        """IDs not matching NG-v<N>-NNNN raise with a specific message.

        Note: by convention (and consistent with the L-2 gold pattern),
        the regex permits any non-empty digit run for the version
        (so v01 is technically accepted). The bad-id list below covers
        the shapes that genuinely fail the pattern.
        """
        for bad_id in [
            "NG-1-0001",          # missing 'v' before version
            "NG-v1-1",            # too few digits
            "NG-v1-00001",        # too many digits
            "ng-v1-0001",         # lowercase ng
            "NG-vX-0001",         # non-numeric version
            "",                   # empty string
            "some-other-id",      # completely different shape
        ]:
            raw = _valid_entry(id=bad_id)
            with pytest.raises(ValueError, match="does not match the required pattern"):
                NarrativeGoldEntry.from_dict(raw)

    def test_from_dict_id_must_be_string(self) -> None:
        """Non-string ids raise."""
        raw = _valid_entry(id=123)
        with pytest.raises(ValueError, match="id must be a string"):
            NarrativeGoldEntry.from_dict(raw)

    def test_from_dict_fen_must_be_string(self) -> None:
        """Non-string fen raises."""
        raw = _valid_entry(fen=42)
        with pytest.raises(ValueError, match="fen must be a string"):
            NarrativeGoldEntry.from_dict(raw)

    def test_from_dict_narrative_must_be_string(self) -> None:
        """Non-string narrative_explanation raises."""
        raw = _valid_entry(narrative_explanation=[])
        with pytest.raises(ValueError, match="narrative_explanation must be a string"):
            NarrativeGoldEntry.from_dict(raw)

    def test_from_dict_narrative_too_short_raises(self) -> None:
        """narrative_explanation shorter than 50 chars is rejected.

        This protects against accidental stubs (typo, paste error)
        sneaking into a future BBF-69.2 hand-curated corpus.
        """
        raw = _valid_entry(narrative_explanation="too short")
        with pytest.raises(ValueError, match="narrative_explanation too short"):
            NarrativeGoldEntry.from_dict(raw)

    def test_from_dict_source_must_be_dict(self) -> None:
        """Non-dict source raises."""
        raw = _valid_entry(source="not a dict")
        with pytest.raises(ValueError, match="source must be a dict"):
            NarrativeGoldEntry.from_dict(raw)

    def test_from_dict_source_must_have_type_field(self) -> None:
        """source dict must include at least the `type` key."""
        raw = _valid_entry()
        raw["source"] = {"title": "no type field"}  # type: ignore[assignment]
        with pytest.raises(
            ValueError, match="source missing required field 'type'"
        ):
            NarrativeGoldEntry.from_dict(raw)


class TestLoadNarrativeGold:
    def test_load_version_required_format(self) -> None:
        """version must be of the form vN (lowercase v + digits).

        By convention (and consistent with the L-2 gold pattern at
        libs/chess_coach/datasets/l2_gold.py), the regex accepts any
        non-empty digit run for the version, so v01 is technically
        valid. The bad-version list below covers the shapes that
        genuinely fail the pattern.
        """
        for bad_version in ("", "v", "V1", "1", "version-1", None, 42):
            with pytest.raises(ValueError, match="version must be"):
                load_narrative_gold(version=bad_version)  # type: ignore[arg-type]

    def test_load_missing_corpus_raises(self, tmp_path) -> None:
        """FileNotFoundError when the corpus file does not exist."""
        with pytest.raises(FileNotFoundError, match="Narrative gold corpus not found"):
            load_narrative_gold(version="v99", base_path=tmp_path)

    def test_load_returns_entries_from_disk(self, tmp_path) -> None:
        """End-to-end load: write a small corpus, load it back."""
        corpus_dir = tmp_path / "v1"
        corpus_dir.mkdir()
        corpus = {
            "schema_version": 1,
            "entries": [_valid_entry("NG-v1-0001"), _valid_entry("NG-v1-0002")],
        }
        (corpus_dir / "corpus.json").write_text(json.dumps(corpus))
        entries = load_narrative_gold(version="v1", base_path=tmp_path)
        assert len(entries) == 2
        assert [e.id for e in entries] == ["NG-v1-0001", "NG-v1-0002"]

    def test_load_with_metadata_preserves_underscore_keys(self, tmp_path) -> None:
        """load_narrative_gold_with_metadata returns the _metadata dict
        so tooling can surface the SYNTHETIC PLACEHOLDER warning.
        """
        corpus_dir = tmp_path / "v1"
        corpus_dir.mkdir()
        corpus = {
            "schema_version": 1,
            "_metadata": {"WARNING": "SYNTHETIC PLACEHOLDER", "size": 5},
            "entries": [_valid_entry()],
        }
        (corpus_dir / "corpus.json").write_text(json.dumps(corpus))
        raw = load_narrative_gold_with_metadata(version="v1", base_path=tmp_path)
        assert raw["_metadata"]["WARNING"] == "SYNTHETIC PLACEHOLDER"
        assert raw["schema_version"] == 1

    def test_load_wrong_schema_version_raises(self, tmp_path) -> None:
        """schema_version must be 1; anything else is rejected."""
        corpus_dir = tmp_path / "v1"
        corpus_dir.mkdir()
        corpus = {
            "schema_version": 99,
            "entries": [_valid_entry()],
        }
        (corpus_dir / "corpus.json").write_text(json.dumps(corpus))
        with pytest.raises(ValueError, match="schema_version 99, expected 1"):
            load_narrative_gold(version="v1", base_path=tmp_path)

    def test_load_missing_entries_key_raises(self, tmp_path) -> None:
        """Top-level corpus dict must have an 'entries' key."""
        corpus_dir = tmp_path / "v1"
        corpus_dir.mkdir()
        (corpus_dir / "corpus.json").write_text(json.dumps({"schema_version": 1}))
        with pytest.raises(ValueError, match="missing the 'entries' key"):
            load_narrative_gold(version="v1", base_path=tmp_path)

    def test_load_top_level_not_object_raises(self, tmp_path) -> None:
        """The corpus must be a JSON object, not a list or scalar."""
        corpus_dir = tmp_path / "v1"
        corpus_dir.mkdir()
        (corpus_dir / "corpus.json").write_text(json.dumps([_valid_entry()]))
        with pytest.raises(ValueError, match="must be a JSON object"):
            load_narrative_gold(version="v1", base_path=tmp_path)


class TestValidateNarrativeGold:
    def test_validate_clean_corpus_returns_no_errors(self) -> None:
        """A well-formed corpus validates with zero errors.

        Each entry uses a different FEN (the default test FEN is
        the starting position; if all 3 share it, the validator
        correctly flags duplicate FENs, which would mask the
        "clean corpus" assertion).
        """
        # Three distinct opening positions, each with a non-trivial
        # difference (move 1, 2, 3 of the King's Pawn).
        fens = [
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
            "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2",
        ]
        corpus = [
            NarrativeGoldEntry.from_dict(
                _valid_entry(f"NG-v1-{i:04d}", fen=fens[i - 1])
            )
            for i in range(1, 4)
        ]
        assert validate_narrative_gold(corpus) == []

    def test_validate_duplicate_ids_returns_error(self) -> None:
        """Two entries with the same id is an error (corpus is ambiguous)."""
        corpus = [
            NarrativeGoldEntry.from_dict(_valid_entry("NG-v1-0001")),
            NarrativeGoldEntry.from_dict(_valid_entry("NG-v1-0001")),  # same id
        ]
        errors = validate_narrative_gold(corpus)
        assert any("duplicate IDs" in e for e in errors)

    def test_validate_duplicate_fens_returns_error(self) -> None:
        """Two entries with the same FEN is an error (narration pipeline
        lookup would be ambiguous).
        """
        corpus = [
            NarrativeGoldEntry.from_dict(
                _valid_entry("NG-v1-0001", fen="8/8/8/8/8/8/8/8 w - - 0 1")
            ),
            NarrativeGoldEntry.from_dict(
                _valid_entry("NG-v1-0002", fen="8/8/8/8/8/8/8/8 w - - 0 1")  # same fen
            ),
        ]
        errors = validate_narrative_gold(corpus)
        assert any("duplicate FENs" in e for e in errors)


class TestListVersions:
    def test_list_versions_returns_sorted_version_dirs(self, tmp_path) -> None:
        """list_versions returns the sorted names of version subdirs
        that contain corpus.json."""
        (tmp_path / "v1").mkdir()
        (tmp_path / "v1" / "corpus.json").write_text("{}")
        (tmp_path / "v2").mkdir()
        (tmp_path / "v2" / "corpus.json").write_text("{}")
        # v99 has no corpus.json -> excluded
        (tmp_path / "v99").mkdir()
        assert list_versions(tmp_path) == ["v1", "v2"]

    def test_list_versions_empty_on_missing_dir(self, tmp_path) -> None:
        """If the base_path doesn't exist, return an empty list."""
        assert list_versions(tmp_path / "does-not-exist") == []


class TestShippedCorpus:
    """Verify the shipped v1 corpus (the SYNTHETIC PLACEHOLDER) loads
    cleanly. This test catches regressions when the user (BBF-69.2)
    replaces the placeholders with real entries.
    """

    def test_shipped_v1_corpus_loads_and_validates(self) -> None:
        """The shipped v1 corpus must load + validate without errors."""
        entries = load_narrative_gold(version="v1")
        assert len(entries) > 0, "shipped v1 corpus must not be empty"
        errors = validate_narrative_gold(entries)
        assert errors == [], f"shipped v1 corpus has validation errors: {errors}"

    def test_shipped_v1_corpus_carries_placeholder_warning(self) -> None:
        """The shipped v1 corpus must include _metadata.WARNING so tooling
        (and humans reading docs) know the entries are placeholders.
        """
        raw = load_narrative_gold_with_metadata(version="v1")
        assert "_metadata" in raw
        assert "WARNING" in raw["_metadata"]
        assert "SYNTHETIC" in raw["_metadata"]["WARNING"].upper()

    def test_shipped_v1_corpus_schema_version_is_1(self) -> None:
        """The shipped v1 corpus must declare schema_version=1."""
        raw = load_narrative_gold_with_metadata(version="v1")
        assert raw["schema_version"] == 1

    def test_shipped_v1_corpus_entries_have_parseable_fens(self) -> None:
        """Every FEN in the shipped corpus must parse as a chess.Board."""
        # Skip if python-chess isn't installed (defensive; per the
        # loader docstring, the module is usable without it).
        pytest.importorskip("chess")
        for entry in load_narrative_gold(version="v1"):
            assert entry.fen_parses(), (
                f"entry {entry.id} has unparseable FEN: {entry.fen!r}"
            )
