#!/usr/bin/env python3
"""Strict completion validator for the BBF-69.2 narrative gold corpus."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import chess

from chess_coach.datasets.narrative_gold import (
    load_narrative_gold,
    load_narrative_gold_with_metadata,
    validate_narrative_gold,
)

_MIN_ENTRIES = 20
_MAX_ENTRIES = 30
_MIN_WORDS = 50
_MAX_WORDS = 200
_PLACEHOLDER_PATTERNS = (
    re.compile(r"\bsynthetic placeholder\b", re.IGNORECASE),
    re.compile(r"\bplaceholder\b", re.IGNORECASE),
    re.compile(r"\bstub\b", re.IGNORECASE),
    re.compile(r"\breplace via bbf-69\.2\b", re.IGNORECASE),
    re.compile(r"\breplace these placeholders\b", re.IGNORECASE),
    re.compile(r"\bn\s*/\s*a\b", re.IGNORECASE),
)
_REQUIRED_SOURCE_FIELDS: dict[str, tuple[str, ...]] = {
    "book": ("title", "author", "chapter", "page"),
    "gm_game": ("title", "author", "event", "year"),
    "online_article": ("title", "author", "url", "accessed"),
}


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in _PLACEHOLDER_PATTERNS)
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    return False


def _source_identity(source_type: str, source: dict[str, Any]) -> tuple[str, ...]:
    """Return a stable type-specific identity for one source work or game."""
    normalized = {
        key: str(value).strip().casefold()
        for key, value in source.items()
        if isinstance(value, str)
    }
    if source_type == "book":
        return (
            source_type,
            normalized.get("title", ""),
            normalized.get("author", ""),
            normalized.get("edition", ""),
        )
    if source_type == "gm_game":
        return (
            source_type,
            normalized.get("title", ""),
            normalized.get("event", ""),
            normalized.get("year", ""),
            normalized.get("round", ""),
        )
    return (
        source_type,
        normalized.get("url", ""),
        normalized.get("title", ""),
        normalized.get("author", ""),
    )


def validate_completion(version: str = "v1", base_path: Path | None = None) -> list[str]:
    """Return strict BBF-69.2 completion errors for one corpus version."""
    errors: list[str] = []

    try:
        raw = load_narrative_gold_with_metadata(version=version, base_path=base_path)
        entries = load_narrative_gold(version=version, base_path=base_path)
    except (FileNotFoundError, ValueError, TypeError) as exc:
        return [str(exc)]

    errors.extend(validate_narrative_gold(entries))

    if not _MIN_ENTRIES <= len(entries) <= _MAX_ENTRIES:
        errors.append(
            f"expected {_MIN_ENTRIES}-{_MAX_ENTRIES} entries, found {len(entries)}"
        )

    metadata = raw.get("_metadata")
    if isinstance(metadata, dict) and "WARNING" in metadata:
        errors.append("_metadata.WARNING must be removed when real curation is complete")
    if _contains_placeholder(raw):
        errors.append("placeholder marker remains in the corpus")

    actual_ids = [entry.id for entry in entries]
    expected_ids = [
        f"NG-{version}-{number:04d}" for number in range(1, len(entries) + 1)
    ]
    if actual_ids != expected_ids:
        errors.append(
            "IDs must be dense and ordered: expected "
            f"{expected_ids[:1]}...{expected_ids[-1:]}, got "
            f"{actual_ids[:1]}...{actual_ids[-1:]}"
        )

    source_types: set[str] = set()
    source_works: set[tuple[str, ...]] = set()
    phase_entries: dict[str, set[str]] = {
        "opening": set(),
        "middlegame": set(),
        "tactical": set(),
        "endgame": set(),
    }

    for entry in entries:
        word_count = len(entry.narrative_explanation.split())
        if not _MIN_WORDS <= word_count <= _MAX_WORDS:
            errors.append(
                f"{entry.id}: narrative_explanation has {word_count} words; "
                f"expected {_MIN_WORDS}-{_MAX_WORDS}"
            )

        try:
            board = chess.Board(entry.fen)
        except (ValueError, AssertionError):
            errors.append(f"{entry.id}: FEN does not parse: {entry.fen!r}")
        else:
            if not board.is_valid():
                errors.append(f"{entry.id}: FEN is not a legal chess position: {entry.fen!r}")

        source_type = entry.source.get("type")
        if not isinstance(source_type, str) or source_type not in _REQUIRED_SOURCE_FIELDS:
            errors.append(
                f"{entry.id}: source.type must be one of "
                f"{sorted(_REQUIRED_SOURCE_FIELDS)}"
            )
        else:
            source_types.add(source_type)
            for field_name in _REQUIRED_SOURCE_FIELDS[source_type]:
                value = entry.source.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    errors.append(
                        f"{entry.id}: source.{field_name} is required for "
                        f"source.type={source_type!r}"
                    )
            source_works.add(_source_identity(source_type, entry.source))

        normalized_tags = {
            tag.casefold() for tag in entry.tags if isinstance(tag, str)
        }
        for phase in phase_entries:
            if phase in normalized_tags:
                phase_entries[phase].add(entry.id)

    if len(entries) >= _MIN_ENTRIES:
        opening_count = len(phase_entries["opening"])
        if opening_count < 5:
            errors.append(f"need at least 5 opening entries, found {opening_count}")
        middlegame_or_tactical = len(
            phase_entries["middlegame"] | phase_entries["tactical"]
        )
        if middlegame_or_tactical < 10:
            errors.append(
                "need at least 10 middlegame/tactical entries, found "
                f"{middlegame_or_tactical}"
            )
        endgame_count = len(phase_entries["endgame"])
        if endgame_count < 5:
            errors.append(f"need at least 5 endgame entries, found {endgame_count}")
        if len(source_types) < 2:
            errors.append(f"need at least 2 source types, found {len(source_types)}")
        if len(source_works) < 3:
            errors.append(f"need at least 3 distinct source works, found {len(source_works)}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate whether narrative gold v1 satisfies BBF-69.2 completion gates."
    )
    parser.add_argument("--version", default="v1", help="corpus version (default: v1)")
    parser.add_argument(
        "--base-path",
        type=Path,
        default=None,
        help="override tests/gold/narrative corpus root",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of human-readable text",
    )
    args = parser.parse_args(argv)

    errors = validate_completion(version=args.version, base_path=args.base_path)
    if args.json:
        print(
            json.dumps(
                {
                    "version": args.version,
                    "complete": not errors,
                    "errors": errors,
                },
                indent=2,
            )
        )
    elif errors:
        print(f"Narrative gold {args.version} is NOT curation-complete:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print(f"Narrative gold {args.version} satisfies all BBF-69.2 completion gates.")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
