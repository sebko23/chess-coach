"""Unit tests for the L-2 gold set loader and validator.

The tests use a small in-memory corpus (no on-disk fixture)
so they are independent of the shipped v1 corpus. A
separate integration-style test verifies that the shipped
v1 corpus loads cleanly and validates.

Mirrors the BBF-43 boot test pattern: a self-contained
test that exercises the public API without depending on
external state.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chess_coach.datasets.l2_gold import (
    L2GoldEntry,
    list_versions,
    load_l2_gold,
    validate_l2_gold,
)


# A minimal valid entry, used as the base for parametric
# tests. Each test that needs a variant copies this and
# overrides the field under test.
def _valid_entry(id: str = "L2-v1-0001", **overrides) -> dict:
    base = {
        "id": id,
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "phase": "opening",
        "best_move_uci": "e2e4",
        "score_cp": 25,
        "source": {
            "type": "opening_theory",
            "name": "Test opening",
            "eco": "C20",
            "move_sequence": "1.e4",
        },
        "engine": {
            "name": "Stockfish",
            "version": "18",
            "depth": 25,
            "multipv": 1,
            "hash_mb": 64,
        },
        "tags": ["test"],
    }
    base.update(overrides)
    return base


class TestL2GoldEntry:
    def test_from_dict_minimal_valid(self):
        """A minimal entry with all required fields parses."""
        entry = L2GoldEntry.from_dict(_valid_entry())
        assert entry.id == "L2-v1-0001"
        assert entry.phase == "opening"
        assert entry.score_cp == 25
        assert entry.tags == ["test"]

    def test_from_dict_default_tags(self):
        """Tags defaults to an empty list when missing."""
        raw = _valid_entry()
        raw.pop("tags")
        entry = L2GoldEntry.from_dict(raw)
        assert entry.tags == []

    def test_from_dict_missing_required_field(self):
        """Each required field is checked; first missing one raises."""
        for missing_field in [
            "id", "fen", "phase", "best_move_uci",
            "score_cp", "source", "engine",
        ]:
            raw = _valid_entry()
            del raw[missing_field]
            with pytest.raises(ValueError, match=f"missing required field {missing_field!r}"):
                L2GoldEntry.from_dict(raw)

    def test_from_dict_invalid_id_pattern(self):
        """The id must match L2-v<N>-<NNNN>."""
        with pytest.raises(ValueError, match="does not match the required pattern"):
            L2GoldEntry.from_dict(_valid_entry(id="not-a-valid-id"))
        with pytest.raises(ValueError, match="does not match the required pattern"):
            L2GoldEntry.from_dict(_valid_entry(id="L2-1-0001"))  # missing v
        with pytest.raises(ValueError, match="does not match the required pattern"):
            L2GoldEntry.from_dict(_valid_entry(id="L2-v1-1"))  # not 4 digits

    def test_from_dict_invalid_phase(self):
        """Phase must be one of opening / middlegame / endgame."""
        with pytest.raises(ValueError, match="phase must be one of"):
            L2GoldEntry.from_dict(_valid_entry(phase="late_middlegame"))

    def test_from_dict_invalid_source_type(self):
        """Source.type must be one of the three known types."""
        with pytest.raises(ValueError, match="source.type must be one of"):
            L2GoldEntry.from_dict(
                _valid_entry(source={"type": "synthetic", "name": "x"})
            )

    def test_from_dict_source_missing_type(self):
        """Source must have a type field."""
        raw = _valid_entry()
        raw["source"] = {"name": "no type field"}
        with pytest.raises(ValueError, match="source missing required field 'type'"):
            L2GoldEntry.from_dict(raw)

    def test_from_dict_engine_missing_required_field(self):
        """Engine must have name, version, depth, multipv."""
        for missing in ["name", "version", "depth", "multipv"]:
            raw = _valid_entry()
            del raw["engine"][missing]
            with pytest.raises(ValueError, match=f"engine missing required field {missing!r}"):
                L2GoldEntry.from_dict(raw)

    def test_from_dict_score_cp_must_be_int(self):
        """score_cp must be an int, not a bool (which is an int subclass)."""
        with pytest.raises(ValueError, match="score_cp must be an int"):
            L2GoldEntry.from_dict(_valid_entry(score_cp="25"))  # string
        with pytest.raises(ValueError, match="score_cp must be an int"):
            L2GoldEntry.from_dict(_valid_entry(score_cp=25.0))  # float
        with pytest.raises(ValueError, match="score_cp must be an int"):
            L2GoldEntry.from_dict(_valid_entry(score_cp=True))  # bool


class TestLoadL2Gold:
    def test_load_l2_gold_invalid_version_format(self):
        """Version must be of the form vN (e.g. v1, v2)."""
        with pytest.raises(ValueError, match="version must be of the form vN"):
            load_l2_gold(version="")
        with pytest.raises(ValueError, match="version must be of the form vN"):
            load_l2_gold(version="1")  # missing v
        with pytest.raises(ValueError, match="version must be of the form vN"):
            load_l2_gold(version="version1")  # wrong format

    def test_load_l2_gold_missing_file(self, tmp_path: Path):
        """Missing corpus file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="L-2 gold corpus not found"):
            load_l2_gold(version="v1", base_path=tmp_path)

    def test_load_l2_gold_must_be_array(self, tmp_path: Path):
        """A corpus file that is not a JSON array raises ValueError."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()
        (version_dir / "corpus.json").write_text(
            json.dumps({"not": "an array"}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="must be a JSON array"):
            load_l2_gold(version="v1", base_path=tmp_path)

    def test_load_l2_gold_happy_path(self, tmp_path: Path):
        """A valid corpus file loads into L2GoldEntry objects."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()
        corpus = [_valid_entry(id="L2-v1-0001"), _valid_entry(id="L2-v1-0002", phase="endgame")]
        (version_dir / "corpus.json").write_text(
            json.dumps(corpus), encoding="utf-8"
        )
        loaded = load_l2_gold(version="v1", base_path=tmp_path)
        assert len(loaded) == 2
        assert loaded[0].id == "L2-v1-0001"
        assert loaded[1].phase == "endgame"

    def test_load_l2_gold_propagates_entry_validation_error(self, tmp_path: Path):
        """A malformed entry in the corpus surfaces as ValueError."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()
        bad = _valid_entry(id="not-a-valid-id")
        (version_dir / "corpus.json").write_text(
            json.dumps([bad]), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="does not match the required pattern"):
            load_l2_gold(version="v1", base_path=tmp_path)

    def test_load_l2_gold_shipped_v1_corpus(self):
        """The shipped tests/gold/L2/v1/corpus.json loads cleanly.

        This is an integration-style check: the on-disk
        corpus is shipped with the repo, so loading it
        should always succeed.
        """
        corpus = load_l2_gold(version="v1")
        assert len(corpus) >= 1, "shipped v1 corpus must not be empty"
        for entry in corpus:
            # Every shipped entry must have a parseable FEN.
            # (Skipped if the ``chess`` package is not
            # installed; the loader handles that case.)
            assert entry.fen_parses(), (
                f"entry {entry.id} has an unparseable FEN: {entry.fen!r}"
            )
            # Every shipped entry must have a legal-looking
            # best_move_uci (4 or 5 chars; standard algebraic
            # move prefixes are 2 chars, plus 0-3 chars for
            # disambiguation and an optional promotion).
            uci = entry.best_move_uci
            assert 4 <= len(uci) <= 5, (
                f"entry {entry.id}: best_move_uci {uci!r} has unexpected length"
            )


class TestValidateL2Gold:
    def test_validate_unique_ids(self):
        """Duplicate IDs surface as a validation error."""
        corpus = [
            L2GoldEntry.from_dict(_valid_entry(id="L2-v1-0001")),
            L2GoldEntry.from_dict(_valid_entry(id="L2-v1-0001")),
        ]
        errors = validate_l2_gold(corpus)
        assert len(errors) == 1
        assert "duplicate IDs" in errors[0]

    def test_validate_unique_ids_ok(self):
        """A corpus with unique IDs has no validation errors."""
        corpus = [
            L2GoldEntry.from_dict(_valid_entry(id="L2-v1-0001")),
            L2GoldEntry.from_dict(_valid_entry(id="L2-v1-0002")),
            L2GoldEntry.from_dict(_valid_entry(id="L2-v1-0003")),
        ]
        errors = validate_l2_gold(corpus)
        assert errors == []

    def test_validate_shipped_v1_corpus(self):
        """The shipped v1 corpus passes the cross-entry validation."""
        corpus = load_l2_gold(version="v1")
        errors = validate_l2_gold(corpus)
        assert errors == [], f"shipped v1 corpus has validation errors: {errors}"


class TestListVersions:
    def test_list_versions_empty_dir(self, tmp_path: Path):
        """An empty base directory returns an empty list."""
        assert list_versions(base_path=tmp_path) == []

    def test_list_versions_nonexistent_dir(self, tmp_path: Path):
        """A non-existent base directory returns an empty list, not an error."""
        nonexistent = tmp_path / "no-such-dir"
        assert list_versions(base_path=nonexistent) == []

    def test_list_versions_finds_v1(self, tmp_path: Path):
        """A base directory with a v1 subdir containing corpus.json returns ['v1']."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()
        (version_dir / "corpus.json").write_text("[]", encoding="utf-8")
        # Also create v2 WITHOUT corpus.json to verify the
        # filter (v2 should not be in the list).
        (tmp_path / "v2").mkdir()
        assert list_versions(base_path=tmp_path) == ["v1"]

    def test_list_versions_shipped(self):
        """The shipped tests/gold/L2/ directory lists v1."""
        versions = list_versions()
        assert "v1" in versions, (
            f"shipped corpus should include v1, got: {versions}"
        )
