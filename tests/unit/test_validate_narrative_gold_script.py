"""Unit tests for the BBF-69.2 narrative-gold completion validator."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.validate_narrative_gold import validate_completion

_FENS = [
    "8/8/8/8/8/8/8/K6k w - - 0 1",
    "8/8/8/8/8/8/1K6/6k1 w - - 0 1",
    "8/8/8/8/8/2K5/8/6k1 w - - 0 1",
    "8/8/8/8/3K4/8/8/6k1 w - - 0 1",
    "8/8/8/4K3/8/8/8/6k1 w - - 0 1",
    "8/8/5K2/8/8/8/8/6k1 w - - 0 1",
    "8/8/6K1/8/8/8/8/5k2 w - - 0 1",
    "8/8/7K/8/8/8/8/5k2 w - - 0 1",
    "8/8/8/7K/8/8/8/5k2 w - - 0 1",
    "8/8/8/8/7K/8/8/5k2 w - - 0 1",
    "8/8/8/8/8/7K/8/5k2 w - - 0 1",
    "8/8/8/8/8/8/7K/4k3 w - - 0 1",
    "8/8/8/8/8/8/6K1/4k3 w - - 0 1",
    "8/8/8/8/8/6K1/8/4k3 w - - 0 1",
    "8/8/8/8/5K2/8/8/4k3 w - - 0 1",
    "8/8/8/6K1/8/8/8/4k3 w - - 0 1",
    "8/8/7K/8/8/8/8/3k4 w - - 0 1",
    "8/8/8/7K/8/8/8/3k4 w - - 0 1",
    "8/8/8/8/7K/8/8/3k4 w - - 0 1",
    "8/8/8/8/8/7K/8/3k4 w - - 0 1",
]


def _explanation(number: int) -> str:
    return (
        f"Position {number} teaches the student to identify the most important imbalance "
        "before calculating variations. First compare king safety, piece activity, pawn "
        "structure, and available breaks. Then choose a plan that improves the least active "
        "piece while limiting the opponent's counterplay. The lesson is to connect a concrete "
        "candidate move to a durable positional reason instead of reacting to superficial threats."
    )


def _complete_corpus() -> dict[str, object]:
    entries = []
    for index, fen in enumerate(_FENS, start=1):
        if index <= 5:
            phase_tag = "opening"
        elif index <= 15:
            phase_tag = "tactical"
        else:
            phase_tag = "endgame"
        source = (
            {
                "type": "book",
                "title": "Source Book One" if index % 4 else "Source Book Two",
                "author": "A. Curator",
                "chapter": f"Chapter {index}",
                "page": str(10 + index),
            }
            if index % 2
            else {
                "type": "gm_game",
                "title": "Player One - Player Two" if index % 4 else "Player Three - Player Four",
                "author": "B. Annotator",
                "event": "Test Event",
                "year": "2026",
            }
        )
        entries.append(
            {
                "id": f"NG-v1-{index:04d}",
                "fen": fen,
                "narrative_explanation": _explanation(index),
                "source": source,
                "tags": [phase_tag, "planning"],
            }
        )
    return {
        "schema_version": 1,
        "_metadata": {"curated_by": "test fixture"},
        "entries": entries,
    }


def _write_corpus(tmp_path: Path, corpus: dict[str, object], version: str = "v1") -> Path:
    base = tmp_path / "narrative"
    version_dir = base / version
    version_dir.mkdir(parents=True)
    (version_dir / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    return base


def test_complete_corpus_passes(tmp_path: Path) -> None:
    base = _write_corpus(tmp_path, _complete_corpus())
    assert validate_completion(base_path=base) == []


def test_shipped_placeholder_corpus_fails_completion_gate() -> None:
    errors = validate_completion()
    assert any("expected 20-30 entries" in error for error in errors)
    assert any("_metadata.WARNING" in error for error in errors)
    assert any("placeholder marker remains" in error for error in errors)


def test_missing_source_field_is_reported(tmp_path: Path) -> None:
    """BBF-87: a `gm_game` source missing its required `event` field
    is reported.  v1's `book.page` rule is no longer enforced (the
    v2 chapter-URL attribution makes `page` optional) so the same
    deletion test against a `book` source now passes cleanly -- we
    assert that here as well.
    """
    corpus = _complete_corpus()
    entries = corpus["entries"]
    assert isinstance(entries, list)
    source = entries[0]["source"]
    assert isinstance(source, dict)
    # Remove `page` (which used to be required).  In v2 this is
    # fine -- `chapter` is the canonical location and the validator
    # no longer complains.
    del source["page"]
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert not any("source.page is required" in e for e in errors), (
        f"book.page should be optional in v2 (chapter URL is the "
        f"canonical location); got errors={errors}"
    )

    # Now test that a `gm_game` source missing `event` is reported.
    # Use a separate sub-tree (and a digit-only version string, which
    # the validator's regex enforces) so we don't collide with the
    # `_write_corpus` call above (which creates tmp_path/narrative/v1).
    base_gm = _write_corpus(tmp_path, _gm_game_corpus_missing_event(), version="v99")
    gm_errors = validate_completion(version="v99", base_path=base_gm)
    assert any("source.event is required" in e for e in gm_errors), (
        f"gm_game source should still require `event`; got errors={gm_errors}"
    )


def _gm_game_corpus_missing_event() -> dict:
    """Build a corpus whose entry uses a gm_game source missing the
    required `event` field.  Used to verify the validator still
    enforces required fields on source types v1 also enforced."""
    from tests.unit.test_validate_narrative_gold_script import _complete_corpus as build
    base = build()
    # Repurpose the first entry as a gm_game with missing `event`.
    base["entries"][0]["source"] = {
        "type": "gm_game",
        "title": "Test GM game",
        "author": "Test GM",
        "year": "2026",
        # NOTE: no `event` field
    }
    return base


def test_word_count_bounds_are_reported(tmp_path: Path) -> None:
    corpus = _complete_corpus()
    entries = corpus["entries"]
    assert isinstance(entries, list)
    entries[0]["narrative_explanation"] = "short " * 11
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert any("has 11 words; expected 50-200" in error for error in errors)


def test_illegal_chess_position_is_reported(tmp_path: Path) -> None:
    corpus = _complete_corpus()
    entries = corpus["entries"]
    assert isinstance(entries, list)
    entries[0]["fen"] = "8/8/8/8/8/8/8/Kk6 w - - 0 1"
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert any("FEN is not a legal chess position" in error for error in errors)


def test_sparse_ids_are_reported(tmp_path: Path) -> None:
    corpus = _complete_corpus()
    entries = corpus["entries"]
    assert isinstance(entries, list)
    entries[-1]["id"] = "NG-v1-0021"
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert any("IDs must be dense and ordered" in error for error in errors)


def test_middlegame_and_tactical_balance_counts_unique_entries(tmp_path: Path) -> None:
    corpus = _complete_corpus()
    entries = corpus["entries"]
    assert isinstance(entries, list)
    for entry in entries[5:15]:
        entry["tags"] = ["opening", "planning"]
    for entry in entries[:5]:
        entry["tags"] = ["opening", "middlegame", "tactical"]
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert any("need at least 10 middlegame/tactical entries, found 5" in error for error in errors)


def test_placeholder_marker_is_recursive(tmp_path: Path) -> None:
    corpus = copy.deepcopy(_complete_corpus())
    entries = corpus["entries"]
    assert isinstance(entries, list)
    source = entries[0]["source"]
    assert isinstance(source, dict)
    source["chapter"] = "PLACEHOLDER"
    base = _write_corpus(tmp_path, corpus)
    errors = validate_completion(base_path=base)
    assert any("placeholder marker remains" in error for error in errors)


def test_bare_stub_and_na_are_placeholder_markers(tmp_path: Path) -> None:
    for marker in ("STUB", "n/a"):
        corpus = copy.deepcopy(_complete_corpus())
        entries = corpus["entries"]
        assert isinstance(entries, list)
        source = entries[0]["source"]
        assert isinstance(source, dict)
        source["chapter"] = marker
        base = _write_corpus(tmp_path / marker.replace("/", "-"), corpus)
        errors = validate_completion(base_path=base)
        assert any("placeholder marker remains" in error for error in errors)


def test_distinct_gm_games_use_event_year_and_round_identity(tmp_path: Path) -> None:
    corpus = _complete_corpus()
    entries = corpus["entries"]
    assert isinstance(entries, list)
    for index, entry in enumerate(entries):
        source = entry["source"]
        assert isinstance(source, dict)
        if source["type"] == "gm_game":
            source["title"] = "Same Players"
            source["event"] = f"Event {index % 3}"
            source["year"] = str(2024 + (index % 2))
            source["round"] = str(index)
    base = _write_corpus(tmp_path, corpus)
    assert validate_completion(base_path=base) == []


def test_shipped_hand_curated_seed_passes() -> None:
    """BBF-89: the shipped 5-entry hand-curated-v0 seed validates under
    the `hand_curated_seed` provenance mode (its own relaxed gates)."""
    errors = validate_completion(version="hand-curated-v0")
    assert errors == [], f"hand-curated-v0 seed should validate: {errors}"


def test_hand_curated_seed_size_gate_is_relaxed(tmp_path: Path) -> None:
    """A small seed (<20 entries, provenance hand_curated_seed) passes."""
    from tests.unit.test_validate_narrative_gold_script import _complete_corpus as build

    corpus = build()
    corpus["entries"] = corpus["entries"][:5]
    corpus["_metadata"] = {"provenance": "hand_curated_seed"}
    for index, entry in enumerate(corpus["entries"], start=1):
        entry["id"] = f"NG-hand-curated-v0-{index:04d}"
    base = tmp_path / "narrative"
    version_dir = base / "hand-curated-v0"
    version_dir.mkdir(parents=True)
    (version_dir / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    errors = validate_completion(version="hand-curated-v0", base_path=base)
    assert errors == [], f"seed should pass relaxed gates: {errors}"


def test_hand_curated_seed_mode_rejects_illegal_fen(tmp_path: Path) -> None:
    """BBF-89: seed mode is not a backdoor — an illegal FEN still fails."""
    from tests.unit.test_validate_narrative_gold_script import _complete_corpus as build

    corpus = build()
    corpus["entries"] = corpus["entries"][:5]
    corpus["_metadata"] = {"provenance": "hand_curated_seed"}
    for index, entry in enumerate(corpus["entries"], start=1):
        entry["id"] = f"NG-hand-curated-v0-{index:04d}"
    corpus["entries"][0]["fen"] = "8/8/8/8/8/8/8/Kk6 w - - 0 1"  # illegal
    base = tmp_path / "narrative"
    version_dir = base / "hand-curated-v0"
    version_dir.mkdir(parents=True)
    (version_dir / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    errors = validate_completion(version="hand-curated-v0", base_path=base)
    assert any("FEN is not a legal chess position" in e for e in errors), errors
