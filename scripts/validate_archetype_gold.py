#!/usr/bin/env python3
"""Strict completion validator for the BBF-75 archetype gold corpus."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from chess_coach.datasets.archetype_gold import (
    load_archetype_gold,
    load_archetype_gold_with_metadata,
    validate_archetype_gold,
)

_MIN_ENTRIES = 20
_MAX_ENTRIES = 40
_ID_PATTERN = re.compile(r"^AG-v\d+-\d{4}$")
_PLACEHOLDER_PATTERNS = (
    re.compile(r"\bsynthetic placeholder\b", re.IGNORECASE),
    re.compile(r"\bplaceholder\b", re.IGNORECASE),
    re.compile(r"\bstub\b", re.IGNORECASE),
    re.compile(r"\breplace via bbf-75\.1\b", re.IGNORECASE),
    re.compile(r"\breplace these placeholders\b", re.IGNORECASE),
    re.compile(r"\bn\s*/\s*a\b", re.IGNORECASE),
)
_STANDARD_LABELS = (
    "Tactician",
    "Positional Player",
    "Grinder",
    "Wildcard",
    "Specialist",
    "Tilter",
    "Endgame Specialist",
)
# `Unknown` is reserved for the kNN output bucket; it MUST NOT appear as
# a corpus label (per BBF-66 design: "Unknown labels always set
# passes_b4_gate=False").
_CORPUS_ALLOWED_LABELS = _STANDARD_LABELS
_REQUIRED_METRICS = (
    "tactical_vs_positional_bias",
    "time_pressure_quality",
    "opening_comfort",
    "conversion_ability",
    "blunder_rate_vs_rating",
    "decision_fatigue",
)
_OPTIONAL_METRICS = ("sequence_based_tilt",)
_MIN_ENTRIES_PER_NON_UNKNOWN_LABEL = 2


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in _PLACEHOLDER_PATTERNS)
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    return False


def _validate_metrics_shape(metric_values: dict[str, Any]) -> list[str]:
    """Return per-entry errors for a single metrics dict."""
    errors: list[str] = []
    for required in _REQUIRED_METRICS:
        value = metric_values.get(required)
        if value is None:
            errors.append(f"missing required metric {required!r}")
            continue
        if not isinstance(value, (int, float)):
            errors.append(f"metric {required!r} is not numeric")
            continue
        if not (-1e6 < float(value) < 1e6):
            errors.append(f"metric {required!r} is out of plausible range")
    for opt in _OPTIONAL_METRICS:
        if opt in metric_values:
            value = metric_values[opt]
            if value is not None and not isinstance(value, (int, float)):
                errors.append(f"optional metric {opt!r} is not numeric")
    return errors


def validate_completion(version: str = "v1", base_path: Path | None = None) -> list[str]:
    """Return strict BBF-75 completion errors for one corpus version."""
    errors: list[str] = []

    try:
        raw = load_archetype_gold_with_metadata(version=version, base_path=base_path)
        entries = load_archetype_gold(version=version, base_path=base_path)
    except (FileNotFoundError, ValueError, TypeError) as exc:
        return [str(exc)]

    errors.extend(validate_archetype_gold(entries))

    for entry in entries:
        errors.extend(
            f"{entry.id}: " + msg
            for msg in _validate_metrics_shape(entry.metrics)
        )

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
        f"AG-{version}-{number:04d}" for number in range(1, len(entries) + 1)
    ]
    if actual_ids != expected_ids:
        errors.append(
            "IDs must be dense and ordered: expected "
            f"{expected_ids[:1]}...{expected_ids[-1:]}, got "
            f"{actual_ids[:1]}...{actual_ids[-1:]}"
        )

    label_counts: Counter[str] = Counter()
    for entry in entries:
        if entry.archetype_label not in _CORPUS_ALLOWED_LABELS:
            errors.append(
                f"{entry.id}: archetype_label {entry.archetype_label!r} is not "
                f"a corpus label; valid labels: "
                f"{', '.join(_CORPUS_ALLOWED_LABELS)}. "
                f"`Unknown` is reserved for the kNN output bucket."
            )
            continue
        label_counts[entry.archetype_label] += 1

    for label in _STANDARD_LABELS:
        if label_counts[label] < _MIN_ENTRIES_PER_NON_UNKNOWN_LABEL:
            errors.append(
                f"need at least {_MIN_ENTRIES_PER_NON_UNKNOWN_LABEL} entries per "
                f"archetype, found {label_counts[label]} for {label!r}"
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate whether archetype gold v1 satisfies BBF-75 completion gates."
    )
    parser.add_argument("--version", default="v1", help="corpus version (default: v1)")
    parser.add_argument(
        "--base-path",
        type=Path,
        default=None,
        help="override tests/gold/archetypes corpus root",
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
        print(f"Archetype gold {args.version} is NOT curation-complete:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print(f"Archetype gold {args.version} satisfies all BBF-75 completion gates.")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
