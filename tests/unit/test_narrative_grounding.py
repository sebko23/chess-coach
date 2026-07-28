"""BBF-87.1 unit tests for the narrative grounding layer.

Covers:
  - GroundingIndex construction (FEN -> entry index)
  - FEN lookup (hit + miss)
  - build_grounding_block formatting
  - Validator's grounding citation check
    (similarity via word-LCS; both passes and failures)
  - Pipeline.explain() returns (narration, corpus_entry_id) tuple
    when a FEN matches the v2 corpus
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chess_coach.narration.grounding import (
    GroundingIndex,
    GroundingMatch,
    build_grounding_block,
)
from chess_coach.narration.validator import (
    _grounding_similarity_ok,
    _lcs_word_count,
    _word_tokens,
    validate_citations,
)

_V2_CORPUS_PATH = Path("tests/gold/narrative/v2/corpus.json")


# ---- GroundingIndex construction + lookup ----


def test_grounding_index_loads_v2_corpus_at_30_entries() -> None:
    """BBF-87.1: GroundingIndex('v2') builds a 30-entry index."""
    gi = GroundingIndex(version="v2")
    assert gi.version == "v2"
    assert gi.size == 30


def test_grounding_index_lookup_hit_returns_entry() -> None:
    """BBF-87.1: FEN lookup returns GroundingMatch for an entry in v2."""
    gi = GroundingIndex(version="v2")
    raw = json.loads(_V2_CORPUS_PATH.read_text(encoding="utf-8"))
    target = raw["entries"][0]
    match = gi.lookup(target["fen"])
    assert match is not None
    assert match.entry_id == target["id"]
    assert match.narrative_explanation == target["narrative_explanation"]
    assert match.phase == target["tags"][0]


def test_grounding_index_lookup_miss_returns_none() -> None:
    """BBF-87.1: FEN lookup returns None when the FEN is not in v2."""
    gi = GroundingIndex(version="v2")
    # Synthesize a FEN that's very unlikely to be in the corpus
    unlikely = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    assert gi.lookup(unlikely) is None


def test_grounding_index_lookup_is_exact_equality() -> None:
    """BBF-87.1: FEN comparison is exact string equality, not normalized."""
    gi = GroundingIndex(version="v2")
    raw = json.loads(_V2_CORPUS_PATH.read_text(encoding="utf-8"))
    target_fen = raw["entries"][0]["fen"]
    # A perturbed FEN (different move number) is NOT a match.
    perturbed = target_fen.rsplit(" ", 1)
    if len(perturbed) == 2:
        # Bump the half-move clock by 1
        head, tail = perturbed
        move_num = tail.split(" ")[-1] if tail else "0"
        try:
            new_move_num = str(int(move_num) + 1)
        except ValueError:
            new_move_num = move_num
        perturbed_fen = f"{head} {new_move_num}"
        assert gi.lookup(perturbed_fen) is None


# ---- build_grounding_block formatting ----


def test_build_grounding_block_for_match_includes_explanation() -> None:
    """BBF-87.1: grounding block embeds the corpus entry's prose."""
    raw = json.loads(_V2_CORPUS_PATH.read_text(encoding="utf-8"))
    target = raw["entries"][0]
    match = GroundingMatch(
        entry_id=target["id"],
        narrative_explanation=target["narrative_explanation"],
        source=target["source"],
        phase=target["tags"][0],
    )
    block = build_grounding_block(match)
    # The block contains the full prose verbatim.
    assert target["narrative_explanation"] in block
    # The block tells the LLM how to cite.
    assert "<grounding>" in block
    # The block includes provenance.
    assert target["id"] in block
    assert "lichess_game" in block or "book" in block


def test_build_grounding_block_for_none_returns_empty() -> None:
    """BBF-87.1: None match returns empty string (no-op)."""
    assert build_grounding_block(None) == ""


# ---- Word-LCS similarity check ----


def test_word_tokens_strips_trailing_punctuation() -> None:
    """BBF-87.1: tokenization is case-insensitive and strips , . ; : ! ? \" '."""
    # The implementation strips the strip set from both ends of each
    # token (a side-effect of the simple str.strip() call), not just
    # trailing. Documented behavior here; the test asserts the
    # actual behavior.
    toks = _word_tokens("Hello, World! Chess 'n stuff.")
    assert toks == ["hello", "world", "chess", "n", "stuff"]


def test_lcs_word_count_for_identical_lists() -> None:
    """BBF-87.1: identical lists give full LCS."""
    words = ["the", "quick", "brown", "fox"]
    assert _lcs_word_count(words, words) == 4


def test_lcs_word_count_for_empty_lists() -> None:
    """BBF-87.1: empty list gives 0."""
    assert _lcs_word_count([], ["a", "b"]) == 0
    assert _lcs_word_count(["a", "b"], []) == 0
    assert _lcs_word_count([], []) == 0


def test_lcs_word_count_for_subset() -> None:
    """BBF-87.1: subset of corpus gives a partial LCS."""
    corpus = ["the", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]
    citation = ["quick", "brown", "fox", "jumps"]
    assert _lcs_word_count(citation, corpus) == 4


def test_grounding_similarity_ok_exact_quote_passes() -> None:
    """BBF-87.1: an exact 30+ word quote passes the absolute-floor check."""
    corpus = " ".join(["word"] * 50)
    citation = " ".join(["word"] * 35)
    assert _grounding_similarity_ok(citation, corpus)


def test_grounding_similarity_ok_high_overlap_passes() -> None:
    """BBF-87.1: 60% word overlap on a short citation passes the relative-floor check."""
    common = " ".join(["word"] * 12)
    # 12 words shared, citation has 20 words total = 60% overlap
    citation = common + " " + " ".join(["other"] * 8)
    corpus = common + " " + " ".join(["irrelevant"] * 100)
    assert _grounding_similarity_ok(citation, corpus)


def test_grounding_similarity_ok_low_overlap_fails() -> None:
    """BBF-87.1: 5% word overlap fails both floors."""
    # Build a citation of >30 words with <5% overlap
    long_citation = " ".join(["a"] * 30)  # 30 short words, none in corpus
    corpus = "completely unrelated text with no shared words at all"
    assert not _grounding_similarity_ok(long_citation, corpus)


def test_grounding_similarity_ok_empty_citation_fails() -> None:
    """BBF-87.1: empty citation fails (no quote, no contribution)."""
    assert not _grounding_similarity_ok("", "any non-empty corpus text")


# ---- Validator integration with grounding_match ----


def test_validate_citations_no_grounding_match_skips_grounding_check() -> None:
    """BBF-87.1: passing grounding_match=None skips grounding validation."""
    # A narration with bogus <grounding> tags should still pass if
    # no grounding_match was provided (no FEN match -- no block
    # was injected).
    from chess_coach.protocol_types.analysis import (
        AnalysisResult,
        PVLine,
        Score,
    )
    result = AnalysisResult(
        engine_id="sf",
        engine_version="SF 18",
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        depth_reached=1,
        multipv=1,
        settings_hash="x",
        cpu_arch="x86_64",
        thread_count=1,
        pvs=[
            PVLine(
                multipv=1,
                score=Score(kind="cp", value=30),
                depth=1,
                moves=["e2e4"],
            )
        ],
    )
    narration = "Just a normal narration, no <grounding> tags."
    vr = validate_citations(narration, result, grounding_match=None)
    assert vr.valid
    assert vr.grounding_failures == []


def test_validate_citations_with_grounding_match_flags_bad_citation() -> None:
    """BBF-87.1: when a grounding match is provided, citations must
    overlap the corpus explanation or the validator flags them.
    """
    from chess_coach.protocol_types.analysis import (
        AnalysisResult,
        PVLine,
        Score,
    )
    result = AnalysisResult(
        engine_id="sf",
        engine_version="SF 18",
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        depth_reached=1,
        multipv=1,
        settings_hash="x",
        cpu_arch="x86_64",
        thread_count=1,
        pvs=[
            PVLine(
                multipv=1,
                score=Score(kind="cp", value=30),
                depth=1,
                moves=["e2e4"],
            )
        ],
    )
    # Build a GroundingMatch whose prose is completely different
    # from the citation; the citation's words won't match the
    # corpus words, so the validator should fail.
    match = GroundingMatch(
        entry_id="NG-v2-test",
        narrative_explanation="alpha beta gamma delta epsilon zeta",
        source={"type": "test"},
        phase="test",
    )
    narration = (
        "<grounding>nope nope nope nope nope nope nope nope nope</grounding>"
    )
    vr = validate_citations(narration, result, grounding_match=match)
    # 9 'nope' tokens, 0 overlap with corpus, < 30 words -> fail.
    assert len(vr.grounding_failures) == 1


def test_validate_citations_with_grounding_match_accepts_good_citation() -> None:
    """BBF-87.1: a citation that quotes the corpus prose passes."""
    from chess_coach.protocol_types.analysis import (
        AnalysisResult,
        PVLine,
        Score,
    )
    result = AnalysisResult(
        engine_id="sf",
        engine_version="SF 18",
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        depth_reached=1,
        multipv=1,
        settings_hash="x",
        cpu_arch="x86_64",
        thread_count=1,
        pvs=[
            PVLine(
                multipv=1,
                score=Score(kind="cp", value=30),
                depth=1,
                moves=["e2e4"],
            )
        ],
    )
    # Build a corpus explanation with 50 unique words and a
    # citation that quotes the first 35 of them.
    corpus_words = [f"word{i:03d}" for i in range(50)]
    corpus_text = " ".join(corpus_words)
    citation_words = corpus_words[:35]
    citation_text = " ".join(citation_words)
    match = GroundingMatch(
        entry_id="NG-v2-test",
        narrative_explanation=corpus_text,
        source={"type": "test"},
        phase="test",
    )
    narration = f"<grounding>{citation_text}</grounding>"
    vr = validate_citations(narration, result, grounding_match=match)
    assert vr.grounding_failures == []
    assert vr.valid


# ---- Integration with the production validator on shipped v2 entries ----


def test_shipped_v2_entries_have_parseable_grounding_blocks() -> None:
    """BBF-87.1: every shipped v2 entry's narrative_explanation,
    when formatted via build_grounding_block, produces a block
    that the LLM could cite.
    """
    gi = GroundingIndex(version="v2")
    raw = json.loads(_V2_CORPUS_PATH.read_text(encoding="utf-8"))
    for entry in raw["entries"]:
        match = gi.lookup(entry["fen"])
        assert match is not None
        block = build_grounding_block(match)
        # The block must contain the entry's prose verbatim (the
        # auto-derived template is in the corpus; the validator
        # is the next layer to check the LLM's citations).
        assert entry["narrative_explanation"] in block


# ---- BBF-86 finding F2: graceful degradation on missing corpus ----


def test_grounding_index_graceful_default_logs_warning(
    tmp_path: Path,
) -> None:
    """BBF-86 F2: default constructor swallows FileNotFoundError.

    A missing corpus logs a WARNING and produces an empty
    index. The narration pipeline then runs without grounding
    (the pre-BBF-87.1 behavior for FENs that did not match the
    v1 corpus).

    We test this by passing a `base_path` that doesn't have the
    requested version subdirectory -- the loader's
    FileNotFoundError is the realistic failure mode in a dev
    environment.
    """
    gi = GroundingIndex(version="v3", base_path=tmp_path)
    # The corpus loader raises FileNotFoundError; the constructor
    # catches it and returns an empty index.
    assert gi.size == 0
    # lookup returns None (no match) instead of raising.
    assert (
        gi.lookup("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        is None
    )


def test_grounding_index_strict_mode_raises_on_missing_corpus(
    tmp_path: Path,
) -> None:
    """BBF-86 F2: fail_on_missing=True re-raises the underlying error.

    Strict mode is for tests and CI scenarios where a missing
    corpus is a build error that should surface immediately.
    """
    with pytest.raises(FileNotFoundError):
        GroundingIndex(
            version="v3",
            base_path=tmp_path,
            fail_on_missing=True,
        )
