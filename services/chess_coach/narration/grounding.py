"""BBF-87.1 narrative grounding layer.

Loads the v2 narrative corpus and indexes it by FEN so the
narration pipeline can look up a FEN's grounding paragraph in
O(1) time. This is the wire between the v2 corpus (shipped in
BBF-87) and the production narration pipeline
(`services/chess_coach/narration/pipeline.py`).

Why this lives here, not in `pipeline.py`:
  - The grounding corpus is loaded once at app startup; the
    pipeline gets a `GroundingIndex` instance, not a file path.
  - The validator at `services/chess_coach/narration/validator.py`
    also needs to call back into the corpus for similarity checks
    on `<grounding>` tags. Sharing one module makes that explicit.
  - The corpus is also the source of `corpus_entry_id` strings
    that show up in the audit table; one module for one shape.

What this module does NOT do:
  - It does NOT modify the LLM router or prompt-tuning layer.
  - It does NOT change the existing engine-analysis validation
    (move + eval citation rules).
  - It does NOT add semantic similarity (heuristic substring only).

Honest disclosures (BBF-87.1 brief §0):
  - The injected `narrative_explanation` text is the BBF-87
    auto-derived template paragraph, NOT a chess expert's voice.
    This module passes that text through unchanged; the brief
    documents it as honest product.
  - By project decision, no real hand-curated v1.human corpus
    will replace this. v2 is the production truth.

See `docs/16_audit/BBF-87.1-wire-narration-pipeline.md` for
the full design.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chess_coach.datasets.narrative_gold import (
    NarrativeGoldEntry,
    load_narrative_gold,
)


@dataclass(frozen=True)
class GroundingMatch:
    """A successful FEN -> entry lookup result.

    Attributes:
        entry_id: The corpus-local id (e.g. "NG-v2-0001"). Used for
            citation validation and audit-table recording.
        narrative_explanation: The 50-200 word coaching paragraph
            from the corpus. Injected into the LLM prompt as a
            grounding block.
        source: Provenance dict (corpus `source` field). Surfaced
            in the prompt for transparency so the LLM can decide
            whether to cite.
        phase: The phase tag (first tag, by corpus convention).
            Used by callers for analytics; not part of the
            grounding-block text.
    """

    entry_id: str
    narrative_explanation: str
    source: dict[str, Any]
    phase: str


class GroundingIndex:
    """O(1) FEN -> corpus-entry index for the v2 narrative corpus.

    Construct once at app startup. The narration pipeline looks
    up FENs in the index for every `/v1/narration/explain` call.

    The index is a `dict[fen, NarrativeGoldEntry]`; FENs are the
    key and are unique by construction (the corpus has no
    duplicate FENs).

    Empty when the corpus is empty or the FEN has no match.
    """

    def __init__(
        self,
        version: str = "v2",
        base_path: Path | None = None,
        fail_on_missing: bool = False,
    ) -> None:
        """Load the v2 corpus once and build the FEN index.

        `version` defaults to "v2" (the auto-derived corpus
        shipped in BBF-87). "v1" still works for backward compat
        (the placeholder corpus); callers that need v1 explicitly
        can pass version="v1".

        `base_path` is forwarded to `load_narrative_gold`; tests
        that build a tmp corpus use it to override the default
        `tests/gold/narrative/` location.

        `fail_on_missing` controls how the constructor handles a
        missing or malformed corpus file:
          - True (strict mode): re-raise the underlying
            FileNotFoundError or ValueError. Use this in tests
            that need to detect the error, and anywhere a
            missing corpus is a build error.
          - False (default, graceful mode): log a WARNING via
            `logging.getLogger(__name__)` and build an empty
            index. The narration pipeline then runs without
            grounding (the pre-BBF-87.1 behavior for FENs that
            didn't match the v1 corpus).

        BBF-86 finding F2 (external review §7.2): gateway
        startup should not crash when the corpus is missing or
        malformed in a local dev / test environment. Production
        deploys ship the corpus via Dockerfile COPY (BBF-87.1 +
        BBF-87.1.y follow-up) so this fallback path is rarely
        hit in production; it exists primarily for dev/test.
        """
        import logging
        logger = logging.getLogger(__name__)

        self._version = version
        try:
            self._entries: list[NarrativeGoldEntry] = load_narrative_gold(
                version, base_path=base_path,
            )
        except (FileNotFoundError, ValueError) as exc:
            if fail_on_missing:
                raise
            logger.warning(
                "BBF-86 finding F2: narrative_gold corpus missing or "
                "malformed for version=%s at base_path=%s (%s: %s); "
                "running without grounding. This is the pre-BBF-87.1 "
                "behavior for FENs that don\'t match the corpus. "
                "Production deploys ship the corpus via Dockerfile "
                "COPY; this fallback is for dev/test environments.",
                version, base_path, type(exc).__name__, exc,
            )
            self._entries = []
        # Index by FEN. FENs are deterministic strings; identical
        # FENs collapse to the same entry. The corpus has at most
        # 1 entry per FEN by convention.
        self._by_fen: dict[str, NarrativeGoldEntry] = {
            entry.fen: entry for entry in self._entries
        }

    @property
    def version(self) -> str:
        """The corpus version this index loaded."""
        return self._version

    @property
    def size(self) -> int:
        """Number of entries in the index."""
        return len(self._entries)

    def lookup(self, fen: str) -> GroundingMatch | None:
        """Return the grounding match for `fen`, or None.

        Lookup is exact FEN string equality. FEN normalization
        is NOT done here -- the corpus stores FENs in the form
        they were captured (with side-to-move, castling rights,
        en-passant, etc.); the route hands us the same FEN the
        user POSTed. If callers want a normalized lookup, they
        normalize before calling.
        """
        entry = self._by_fen.get(fen)
        if entry is None:
            return None
        return GroundingMatch(
            entry_id=entry.id,
            narrative_explanation=entry.narrative_explanation,
            source=entry.source,
            # The phase tag is the first element of the tag list
            # by corpus convention; defensive default if empty.
            phase=entry.tags[0] if entry.tags else "unknown",
        )


def build_grounding_block(match: GroundingMatch | None) -> str:
    """Format a GroundingMatch for LLM prompt injection.

    Returns an empty string if `match is None` (no FEN match;
    pipeline behavior is unchanged from the no-grounding case).

    The block is a single multi-line string that the prompt
    builder prepends to the user prompt's ENGINE ANALYSIS block.
    The block ends with a hint about how the LLM should cite it
    (via `<grounding>...</grounding>` tags).
    """
    if match is None:
        return ""
    src = match.source
    # Source attribution. The dict shape is type-specific; the
    # brief documents this as a v2-corpus schema (`type` is always
    # present, plus per-type fields like `game_id` for lichess_game
    # or `chapter_url` for book). We render a compact one-liner
    # so the LLM can decide what to cite.
    src_summary = _summarize_source(src)
    return (
        "NARRATIVE GROUNDING (auto-derived; cite from this if "
        "relevant, using <grounding>...</grounding> tags around "
        "any quoted or paraphrased sentences):\n"
        f"{match.narrative_explanation}\n"
        f"Source: {src_summary} (corpus id: {match.entry_id})"
    )


def _summarize_source(source: dict[str, Any]) -> str:
    """Render a one-line source summary for the grounding block.

    The `type` field is always present. We pick a few
    well-known fields per type and ignore the rest so the LLM
    isn't overwhelmed.
    """
    stype = source.get("type", "unknown")
    if stype == "lichess_game":
        return (
            f"lichess_game "
            f"(game_id={source.get('game_id', '?')}, "
            f"opening={source.get('opening', '?')}, "
            f"ECO={source.get('eco', '?')})"
        )
    if stype == "book":
        return (
            f"book (title={source.get('title', '?')}, "
            f"author={source.get('author', '?')}, "
            f"chapter={source.get('chapter', '?')})"
        )
    return f"{stype} (no summary available)"


__all__ = [
    "GroundingIndex",
    "GroundingMatch",
    "build_grounding_block",
]
