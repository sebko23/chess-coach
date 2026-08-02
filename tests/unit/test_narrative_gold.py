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
import logging
from pathlib import Path

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


class TestShippedCorpusV2:
    """BBF-87: verify the shipped v2 (auto-derived) corpus loads cleanly.

    The v2 corpus is structurally distinct from v1:
      - Generated by scripts/curate_narrative_gold_auto.py.
      - Two source types: `lichess_game` (user PGN attribution) and
        `book` (Fischer 60-Memorable-Games chapter-URL attribution).
      - `_metadata.provenance = "auto"` flags the corpus as
        auto-derived (different from v1's hand-curation gap).
      - `book.source.page` is optional (chapter URL is enough for
        lichess study reformat attribution).

    These tests do NOT exercise the validator CLI
    (scripts/validate_narrative_gold.py) -- only the in-memory
    loader / validator pair in libs/chess_coach/datasets/...
    """

    def test_shipped_v2_corpus_loads_and_validates(self) -> None:
        """Shipped v2 corpus must load + cross-entry validate (id + fen uniqueness)."""
        entries = load_narrative_gold(version="v2")
        assert len(entries) >= 20, (
            f"shipped v2 corpus must have >=20 entries; got {len(entries)}"
        )
        errors = validate_narrative_gold(entries)
        assert errors == [], f"shipped v2 corpus has validation errors: {errors}"

    def test_shipped_v2_corpus_schema_version_is_1(self) -> None:
        """schema_version=1, same wire format as v1."""
        raw = load_narrative_gold_with_metadata(version="v2")
        assert raw["schema_version"] == 1

    def test_shipped_v2_corpus_marks_provenance_auto(self) -> None:
        """_metadata.provenance must be 'auto' so the strict validator
        demotes its placeholder-marker rules to advisory."""
        raw = load_narrative_gold_with_metadata(version="v2")
        assert raw["_metadata"].get("provenance") == "auto"

    def test_shipped_v2_corpus_entries_have_parseable_fens(self) -> None:
        """Every FEN must parse via python-chess if available."""
        pytest.importorskip("chess")
        for entry in load_narrative_gold(version="v2"):
            assert entry.fen_parses(), (
                f"entry {entry.id} has unparseable FEN: {entry.fen!r}"
            )

    def test_shipped_v2_corpus_has_both_source_types(self) -> None:
        """BBF-87 brief requires >=2 source types for strict-mode
        compliance. The shipped corpus must carry both `lichess_game`
        and `book` entries."""
        entries = load_narrative_gold(version="v2")
        source_types = {e.source.get("type") for e in entries}
        assert "lichess_game" in source_types, (
            f"missing lichess_game source: types={source_types}"
        )
        assert "book" in source_types, (
            f"missing book source: types={source_types}"
        )

    def test_shipped_v2_corpus_phase_distribution_covers_three_phases(self) -> None:
        """Phase tags must include 'opening', 'middlegame', 'endgame'
        so the strict validator's phase-balance rule clears."""
        entries = load_narrative_gold(version="v2")
        all_tags = {t for e in entries for t in e.tags}
        for phase in ("opening", "middlegame", "endgame"):
            assert phase in all_tags, (
                f"missing phase tag {phase!r}; tags seen={all_tags}"
            )


class TestBBF87SourceTypeSchemas:
    """BBF-87: round-trip the new `lichess_game` source type through
    the loader; verify `book.page` is now optional for chapter-URL
    attribution."""

    def test_lichess_game_source_with_engine_dict_loads(self) -> None:
        """`lichess_game` source carries a non-empty `engine` dict
        (matching the L-2 schema), not a string."""
        raw = _valid_entry(
            "NG-v2-9001",
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            source={
                "type": "lichess_game",
                "game_id": "abc123",
                "site": "https://lichess.org/abc123",
                "white": "player_a",
                "black": "player_b",
                "date": "2026.02.27",
                "engine": {
                    "name": "lichess cloud-eval",
                    "backend": "Stockfish 18",
                    "depth": 22,
                    "source": "lichess",
                },
            },
        )
        entry = NarrativeGoldEntry.from_dict(raw)
        assert entry.source["type"] == "lichess_game"
        assert isinstance(entry.source["engine"], dict)
        assert entry.source["engine"]["depth"] == 22

    def test_book_source_without_page_loads(self) -> None:
        """BBF-87: `book.page` is optional; chapter-URL is sufficient
        for lichess study reformat attribution."""
        raw = _valid_entry(
            "NG-v2-9002",
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            source={
                "type": "book",
                "title": "My 60 Memorable Games",
                "author": "Bobby Fischer",
                "chapter": "https://lichess.org/study/JulEnk3S/A3l1SvqS",
                # NB: no `page` field. The validator passes.
            },
        )
        entry = NarrativeGoldEntry.from_dict(raw)
        assert entry.source["type"] == "book"
        assert "page" not in entry.source
        assert "chapter" in entry.source


# ---- BBF-86.7: self-describing _metadata.version + advisory loader check ----


class TestBBF867VersionField:
    """BBF-86.7: every corpus _metadata declares its own version;
    loader logs an advisory WARNING on mismatch without refusing."""

    def test_v2_shipped_corpus_has_version_field(self) -> None:
        """The shipped v2 narrative corpus self-describes as v2."""
        from chess_coach.datasets.narrative_gold import (
            load_narrative_gold_with_metadata,
        )
        raw = load_narrative_gold_with_metadata(version="v2")
        metadata = raw.get("_metadata")
        assert isinstance(metadata, dict)
        assert metadata.get("version") == "v2"

    def test_v2_loader_no_warning_when_requested_matches(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Requesting v2 from a v2 corpus emits no mismatch WARNING."""
        from chess_coach.datasets.narrative_gold import (
            load_narrative_gold,
        )
        with caplog.at_level(
            "WARNING", logger="chess_coach.datasets.narrative_gold",
        ):
            load_narrative_gold(version="v2")
        mismatch_records = [
            r for r in caplog.records
            if "version mismatch" in r.message.lower()
        ]
        assert not mismatch_records, (
            f"unexpected version-mismatch WARNING(s): "
            f"{[r.message for r in mismatch_records]}"
        )

    def test_v2_loader_warns_when_requested_v1_against_v2_corpus(
        self, caplog: pytest.LogCaptureFixture, tmp_path: Path,
    ) -> None:
        """Requesting v1 from a v2 corpus (or vice versa) logs a
        WARNING but does NOT raise. This is the soft-advisory
        contract the BBF-86.7 brief amended to avoid breaking
        production (e.g. GroundingIndex fallback to v1).
        """
        from chess_coach.datasets.narrative_gold import load_narrative_gold

        # Build a tmp corpus that self-describes as "v2" but is
        # loaded under a different version request ("v1"). The
        # loader must log a WARNING and return entries, not raise.
        tmp_corpus = {
            "schema_version": 1,
            "_metadata": {
                "version": "v2",
                "provenance": "auto",
                "WARNING": "test fixture",
            },
            "entries": [
                {
                    "id": "NG-v2-0001",
                    "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                    "narrative_explanation": (
                        "Test fixture entry. The lesson is to identify the "
                        "key tactical motifs in the position before "
                        "calculating variations, comparing king safety and "
                        "piece activity to develop a coherent plan."
                    ),
                    "source": {"type": "book", "title": "Test", "author": "T", "chapter": "C"},
                    "tags": ["test"],
                },
            ],
        }
        corpus_dir = tmp_path / "v1"
        corpus_dir.mkdir()
        (corpus_dir / "corpus.json").write_text(
            json.dumps(tmp_corpus), encoding="utf-8",
        )

        with caplog.at_level(
            logging.WARNING, logger="chess_coach.datasets.narrative_gold",
        ):
            entries = load_narrative_gold(version="v1", base_path=tmp_path)

        # The loader must succeed (soft-advisory, not refusing).
        assert len(entries) == 1
        assert entries[0].id == "NG-v2-0001"

        # And a version-mismatch WARNING must be logged.
        mismatch = [
            r for r in caplog.records
            if "version mismatch" in r.message.lower()
        ]
        assert mismatch, "expected a version-mismatch WARNING to be logged"
