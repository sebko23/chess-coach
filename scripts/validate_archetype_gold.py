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
# BBF-88.x: auto-derived corpora (provenance == "auto") ship with
# whatever the kNN-bootstrap produced, which is structurally
# smaller than 20 entries (typically 8-14). The strict size rule
# is relaxed for these corpora.
_MIN_AUTO_ENTRIES = 1
_MAX_AUTO_ENTRIES = 30
# BBF-88.2a: per-entry provenance strategy. kNN-bootstrapped
# entries from BBF-88.x use the default strategy. Hand-curated
# entries use "synthetic_shape_curated" and must include an
# `archetype_trait_source` field documenting the source.
_SHAPE_CURATED_STRATEGY = "synthetic_shape_curated"
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

    metadata = raw.get("_metadata")
    is_auto = (
        isinstance(metadata, dict)
        and metadata.get("provenance") == "auto"
    )

    for entry in entries:
        errors.extend(
            f"{entry.id}: " + msg
            for msg in _validate_metrics_shape(entry.metrics)
        )

    # BBF-88.2a: shape-curated entries require an archetype_trait_source.
    # The validator logs a WARNING so operators see the new strategy
    # in their validation output; the WARNING is advisory only and
    # does not fail the corpus.
    shape_curated_count = 0
    for entry in entries:
        prov = entry._provenance
        if not isinstance(prov, dict):
            continue
        if prov.get("strategy") != _SHAPE_CURATED_STRATEGY:
            continue
        shape_curated_count += 1
        source = prov.get("archetype_trait_source")
        if not isinstance(source, str) or not source:
            errors.append(
                f"{entry.id}: shape-curated entry missing "
                f"`archetype_trait_source` in _provenance"
            )
    if shape_curated_count > 0:
        print(
            f"WARNING: {shape_curated_count} shape-curated entry/entries "
            f"(strategy={_SHAPE_CURATED_STRATEGY!r}) are not kNN-bootstrapped; "
            f"metric vectors are hand-curated from the ARCHETYPE_TRAITS shape contract. "
            f"See BBF-88.2a brief for the rationale and BBF-89 for the "
            f"eventual hand-curated seed corpus.",
            file=sys.stderr,
        )

    if is_auto:
        # Auto corpora have their own size floor/ceiling; the
        # hand-curated rule below does not apply.
        if not _MIN_AUTO_ENTRIES <= len(entries) <= _MAX_AUTO_ENTRIES:
            errors.append(
                f"auto corpus: expected {_MIN_AUTO_ENTRIES}-{_MAX_AUTO_ENTRIES} "
                f"entries, found {len(entries)}"
            )
    else:
        if not _MIN_ENTRIES <= len(entries) <= _MAX_ENTRIES:
            errors.append(
                f"expected {_MIN_ENTRIES}-{_MAX_ENTRIES} entries, found {len(entries)}"
            )

    if isinstance(metadata, dict) and "WARNING" in metadata:
        if is_auto:
            # Auto corpora keep their _metadata.WARNING as a
            # structural honesty disclosure ("AUTO-DERIVED. ...").
            # The placeholder marker remains advisory only.
            pass
        else:
            errors.append(
                "_metadata.WARNING must be removed when real curation is complete"
            )
    if _contains_placeholder(raw) and not is_auto:
        errors.append("placeholder marker remains in the corpus")

    if is_auto:
        # Auto corpora do not require dense-and-ordered IDs;
        # the kNN-bootstrap emits entries grouped by archetype
        # with non-contiguous id slots (each archetype reserves
        # a contiguous range). Dense-id enforcement is a v1
        # hand-curation rule.
        pass
    else:
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
            if is_auto:
                # Auto corpora may carry `Unknown` labels because
                # the kNN-bootstrap can land there when no v1
                # reference is close enough. We document it but
                # don't fail the corpus.
                label_counts["Unknown"] += 1
                continue
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
            if is_auto:
                # Auto corpora may not cover all 7 archetypes;
                # the kNN-bootstrap produces whatever archetypes
                # the metric vectors cluster into. Missing
                # archetypes are a documented honest limit, not
                # a completion failure.
                continue
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
