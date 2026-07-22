#!/usr/bin/env python3
"""Combined curation-status dashboard for the chess-coach gold corpora.

Calls both BBF-69.2 narrative-gold and BBF-75 archetype-gold completion
validators and emits a single JSON document summarising the curation
state across both corpora. Used as a one-shot dashboard for the
chess-coach-curation cron and as a programmatic status import for
future BBFs (BBF-69.3, BBF-75.x).

Both validators resolve the corpus at <base_path>/<version>/corpus.json.
The canonical base paths are <repo>/tests/gold/archetypes and
<repo>/tests/gold/narrative; for tests that need to substitute custom
corpora, pass per-corpus override paths via the CLI flags or the
collect_status() kwargs.

Exit code:
  0 — at least one selected corpus is complete (default; matches the
      cron-friendly semantic of "show me what's done").
  1 — none of the selected corpora are complete.
  2 — invocation / configuration error.
  --strict: 0 iff every selected corpus is complete; 1 otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add the repo root to sys.path so `scripts.validate_*` resolves when
# this file is run as a script via `python scripts/curation_status.py`.
# Must run BEFORE the imports below (Python adds the script's directory,
# not the repo root, when a script is invoked directly).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# Sanity-check the import location to surface a clear error early
# instead of letting a downstream ImportError confuse the next person.
if not (_REPO_ROOT / "scripts" / "validate_archetype_gold.py").is_file():
    sys.stderr.write(
        f"curation_status.py: cannot locate scripts/validate_archetype_gold.py "
        f"relative to repo root {_REPO_ROOT}.\n"
    )
    sys.exit(2)

import argparse  # noqa: E402
import json  # noqa: E402
from typing import Any  # noqa: E402

from scripts.validate_archetype_gold import validate_completion as validate_archetype  # noqa: E402
from scripts.validate_narrative_gold import validate_completion as validate_narrative  # noqa: E402

_CORPORA: dict[str, Any] = {
    "archetype_gold": validate_archetype,
    "narrative_gold": validate_narrative,
}


def _status_for(
    corpus: str,
    version: str,
    base_path: Path | None,
) -> dict[str, Any]:
    """Run one validator and return its dashboard-shaped dict."""
    if corpus not in _CORPORA:
        raise ValueError(
            f"unknown corpus {corpus!r}; expected one of {sorted(_CORPORA)}"
        )
    validator = _CORPORA[corpus]
    errors = validator(version=version, base_path=base_path)
    return {
        "version": version,
        "complete": not errors,
        "errors": errors,
    }


def collect_status(
    version: str = "v1",
    archetype_base_path: Path | None = None,
    narrative_base_path: Path | None = None,
    corpora: list[str] | None = None,
) -> dict[str, Any]:
    """Collect per-corpus status and return the combined dashboard dict.

    Each per-corpus base path defaults to the validator's own default
    (i.e. the canonical <repo>/tests/gold/<corpus-name>/ root). Tests
    that need custom corpora pass per-corpus overrides.
    """
    if corpora is None:
        corpora = sorted(_CORPORA)

    # Validate corpus names before iteration so unknown corpora surface
    # a clean ValueError instead of a KeyError from per_corpus_base.
    unknown = [c for c in corpora if c not in _CORPORA]
    if unknown:
        raise ValueError(
            f"unknown corpus(es) {unknown}; expected one of {sorted(_CORPORA)}"
        )

    per_corpus_base: dict[str, Path | None] = {
        "archetype_gold": archetype_base_path,
        "narrative_gold": narrative_base_path,
    }

    out: dict[str, Any] = {}
    for corpus in corpora:
        out[corpus] = _status_for(corpus, version, per_corpus_base[corpus])

    complete_count = sum(1 for v in out.values() if v["complete"])
    total = len(out)
    overall_complete = complete_count == total
    summary = (
        f"{total} corpora checked; {complete_count} complete, "
        f"{total - complete_count} incomplete"
    )
    return {
        "complete": overall_complete,
        "summary": summary,
        "corpora": out,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Combined BBF-69.2 narrative-gold + BBF-75 archetype-gold "
            "curation-status dashboard."
        )
    )
    parser.add_argument("--version", default="v1", help="corpus version (default: v1)")
    parser.add_argument(
        "--archetype-base-path",
        type=Path,
        default=None,
        help=(
            "override archetype-gold corpus root "
            "(forwarded as base_path to the archetype validator)"
        ),
    )
    parser.add_argument(
        "--narrative-base-path",
        type=Path,
        default=None,
        help=(
            "override narrative-gold corpus root "
            "(forwarded as base_path to the narrative validator)"
        ),
    )
    parser.add_argument(
        "--corpus",
        action="append",
        choices=sorted(_CORPORA),
        default=None,
        help=(
            "restrict to one corpus (repeatable). Default: all. "
            "Example: --corpus archetype_gold"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of human-readable text",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "exit 0 only if EVERY selected corpus is complete "
            "(default: exit 0 if at least one selected corpus is "
            "complete; exit 1 if all selected corpora are incomplete)"
        ),
    )
    args = parser.parse_args(argv)

    try:
        dashboard = collect_status(
            version=args.version,
            archetype_base_path=args.archetype_base_path,
            narrative_base_path=args.narrative_base_path,
            corpora=args.corpus,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(dashboard, indent=2))
    else:
        print(f"== chess-coach curation status ({args.version}) ==\n")
        for corpus_name, status in dashboard["corpora"].items():
            verdict = "COMPLETE" if status["complete"] else "INCOMPLETE"
            print(f"[{verdict}] {corpus_name} {status['version']}")
            for error in status["errors"]:
                print(f"  - {error}")
            print()
        print(dashboard["summary"])

    # Exit semantics: default is permissive (0 if at least one complete,
    # 1 if none complete). --strict requires all-complete.
    if args.strict:
        return 0 if dashboard["complete"] else 1
    any_complete = any(s["complete"] for s in dashboard["corpora"].values())
    return 0 if any_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
