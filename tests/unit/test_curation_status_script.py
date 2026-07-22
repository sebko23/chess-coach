"""Unit tests for scripts/curation_status.py (BBF-78 dashboard wrapper).

Covers:
- collect_status() dashboard shape with both corpora complete
- collect_status() dashboard shape with one complete + one incomplete
- per-corpus base_path override (the test-fixture layout differs from
  the canonical tests/gold/... layout, so this is the supported way
  to substitute custom corpora for tests)
- --corpus filter restricts which corpora are queried
- --strict exit semantics (0 only if all selected corpora complete)
- default permissive exit semantics (0 if at least one complete)
- main() argv parsing and JSON output
- main() unknown --corpus -> exit 2
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Importing the wrapper requires the repo root on sys.path so that
# `scripts.validate_*` resolves. The wrapper's __main__ shim does
# this automatically when invoked as a script, but here we import
# it as a module.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.curation_status import collect_status  # noqa: E402

# ----- Archetype gold corpus fixture (mirrors test_validate_archetype_gold_script.py) -----

_ARCHETYPE_LABELS = (
    "Tactician",
    "Positional Player",
    "Grinder",
    "Wildcard",
    "Specialist",
    "Tilter",
    "Endgame Specialist",
)


def _archetype_entry(idx: int, label: str) -> dict[str, object]:
    return {
        "id": f"AG-v1-{idx:04d}",
        "archetype_label": label,
        "metrics": {
            "tactical_vs_positional_bias": 0.50,
            "time_pressure_quality": 0.10,
            "opening_comfort": 20,
            "conversion_ability": 0.60,
            "blunder_rate_vs_rating": 0.15,
            "decision_fatigue": 0.05,
            "sequence_based_tilt": 0.05,
        },
    }


def _archetype_complete_corpus() -> dict[str, object]:
    entries: list[dict[str, object]] = []
    plan = [(label, 4) for label in _ARCHETYPE_LABELS]
    counter = 1
    for label, count in plan:
        for _ in range(count):
            entries.append(_archetype_entry(counter, label))
            counter += 1
    return {
        "schema_version": 1,
        "_metadata": {"curated_by": "test fixture"},
        "entries": entries,
    }


def _archetype_placeholder_corpus() -> dict[str, object]:
    """The shipped 14-entry placeholder must fail the strict validator."""
    return {
        "schema_version": 1,
        "_metadata": {"WARNING": "SYNTHETIC PLACEHOLDER; replace via BBF-75.1"},
        "entries": [
            _archetype_entry(idx, _ARCHETYPE_LABELS[(idx - 1) % len(_ARCHETYPE_LABELS)])
            for idx in range(1, 15)
        ],
    }


def _write_archetype_corpus(tmp_path: Path, corpus: dict[str, object]) -> Path:
    """Write a corpus at <tmp_path>/archetypes/v1/corpus.json and return
    the base path the validator expects (the parent of <version>/)."""
    base = tmp_path / "archetypes"
    (base / "v1").mkdir(parents=True)
    (base / "v1" / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    return base


# ----- Narrative gold corpus fixture (mirrors test_validate_narrative_gold_script.py) -----

_NARRATIVE_FENS = [
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


def _narrative_explanation(number: int) -> str:
    return (
        f"Position {number} teaches the student to identify the most important imbalance "
        "before calculating variations. First compare king safety, piece activity, pawn "
        "structure, and available breaks. Then choose a plan that improves the least active "
        "piece while limiting the opponent's counterplay. The lesson is to connect a concrete "
        "candidate move to a durable positional reason instead of reacting to superficial threats."
    )


def _narrative_complete_corpus() -> dict[str, object]:
    entries = []
    for index, fen in enumerate(_NARRATIVE_FENS, start=1):
        if index <= 5:
            phase_tag = "opening"
        elif index <= 15:
            phase_tag = "tactical"
        else:
            phase_tag = "endgame"
        source: dict[str, object]
        if index % 2:
            source = {
                "type": "book",
                "title": "Source Book One" if index % 4 else "Source Book Two",
                "author": "A. Curator",
                "chapter": f"Chapter {index}",
                "page": str(10 + index),
            }
        else:
            source = {
                "type": "gm_game",
                "title": "Player One - Player Two" if index % 4 else "Player Three - Player Four",
                "author": "B. Annotator",
                "event": "Test Event",
                "year": "2026",
            }
        entries.append({
            "id": f"NG-v1-{index:04d}",
            "fen": fen,
            "narrative_explanation": _narrative_explanation(index),
            "source": source,
            "tags": [phase_tag, "planning"],
        })
    return {
        "schema_version": 1,
        "_metadata": {"curated_by": "test fixture"},
        "entries": entries,
    }


def _narrative_placeholder_corpus() -> dict[str, object]:
    return {
        "schema_version": 1,
        "_metadata": {"WARNING": "SYNTHETIC PLACEHOLDER; replace via BBF-69.2"},
        "entries": [],
    }


def _write_narrative_corpus(tmp_path: Path, corpus: dict[str, object]) -> Path:
    base = tmp_path / "narrative"
    (base / "v1").mkdir(parents=True)
    (base / "v1" / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    return base


# ----- collect_status() unit tests -----


def test_collect_status_both_complete(tmp_path: Path) -> None:
    arch_base = _write_archetype_corpus(tmp_path, _archetype_complete_corpus())
    narr_base = _write_narrative_corpus(tmp_path, _narrative_complete_corpus())

    dashboard = collect_status(
        archetype_base_path=arch_base,
        narrative_base_path=narr_base,
    )

    assert dashboard["complete"] is True
    assert dashboard["summary"] == "2 corpora checked; 2 complete, 0 incomplete"
    assert set(dashboard["corpora"]) == {"archetype_gold", "narrative_gold"}
    for status in dashboard["corpora"].values():
        assert status["complete"] is True
        assert status["errors"] == []


def test_collect_status_archetype_complete_narrative_placeholder(tmp_path: Path) -> None:
    arch_base = _write_archetype_corpus(tmp_path, _archetype_complete_corpus())
    narr_base = _write_narrative_corpus(tmp_path, _narrative_placeholder_corpus())

    dashboard = collect_status(
        archetype_base_path=arch_base,
        narrative_base_path=narr_base,
    )

    assert dashboard["complete"] is False
    assert dashboard["summary"] == "2 corpora checked; 1 complete, 1 incomplete"
    assert dashboard["corpora"]["archetype_gold"]["complete"] is True
    assert dashboard["corpora"]["narrative_gold"]["complete"] is False
    assert dashboard["corpora"]["narrative_gold"]["errors"]


def test_collect_status_archetype_placeholder_narrative_complete(tmp_path: Path) -> None:
    arch_base = _write_archetype_corpus(tmp_path, _archetype_placeholder_corpus())
    narr_base = _write_narrative_corpus(tmp_path, _narrative_complete_corpus())

    dashboard = collect_status(
        archetype_base_path=arch_base,
        narrative_base_path=narr_base,
    )

    assert dashboard["complete"] is False
    assert dashboard["corpora"]["archetype_gold"]["complete"] is False
    assert dashboard["corpora"]["narrative_gold"]["complete"] is True


def test_collect_status_both_placeholder(tmp_path: Path) -> None:
    arch_base = _write_archetype_corpus(tmp_path, _archetype_placeholder_corpus())
    narr_base = _write_narrative_corpus(tmp_path, _narrative_placeholder_corpus())

    dashboard = collect_status(
        archetype_base_path=arch_base,
        narrative_base_path=narr_base,
    )

    assert dashboard["complete"] is False
    assert dashboard["summary"] == "2 corpora checked; 0 complete, 2 incomplete"


def test_collect_status_corpus_filter_restricts_results(tmp_path: Path) -> None:
    arch_base = _write_archetype_corpus(tmp_path, _archetype_complete_corpus())
    narr_base = _write_narrative_corpus(tmp_path, _narrative_complete_corpus())

    dashboard = collect_status(
        archetype_base_path=arch_base,
        narrative_base_path=narr_base,
        corpora=["archetype_gold"],
    )

    assert set(dashboard["corpora"]) == {"archetype_gold"}
    assert dashboard["summary"] == "1 corpora checked; 1 complete, 0 incomplete"
    assert dashboard["complete"] is True


def test_collect_status_version_propagates(tmp_path: Path) -> None:
    """`version` is forwarded to both validators and surfaced in the
    dashboard."""
    arch_base = _write_archetype_corpus(tmp_path, _archetype_complete_corpus())
    narr_base = _write_narrative_corpus(tmp_path, _narrative_complete_corpus())

    dashboard = collect_status(
        version="v1",
        archetype_base_path=arch_base,
        narrative_base_path=narr_base,
    )
    for status in dashboard["corpora"].values():
        assert status["version"] == "v1"


# ----- main() CLI tests -----


def _run_cli(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke the wrapper as a subprocess so the __main__ sys.path shim runs."""
    return subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "curation_status.py"), *argv],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )


def test_cli_json_emits_dashboard(tmp_path: Path) -> None:
    arch_base = _write_archetype_corpus(tmp_path, _archetype_complete_corpus())
    narr_base = _write_narrative_corpus(tmp_path, _narrative_complete_corpus())

    proc = _run_cli([
        "--json",
        "--archetype-base-path", str(arch_base),
        "--narrative-base-path", str(narr_base),
    ])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["complete"] is True
    assert set(payload["corpora"]) == {"archetype_gold", "narrative_gold"}


def test_cli_exit_code_default_permissive(tmp_path: Path) -> None:
    """Default exit semantics: 0 if at least one corpus complete, 1 if none."""
    arch_base = _write_archetype_corpus(tmp_path, _archetype_complete_corpus())
    narr_base = _write_narrative_corpus(tmp_path, _narrative_placeholder_corpus())

    proc = _run_cli([
        "--json",
        "--archetype-base-path", str(arch_base),
        "--narrative-base-path", str(narr_base),
    ])
    # One complete -> 0
    assert proc.returncode == 0

    arch_base2 = _write_archetype_corpus(
        tmp_path / "all_placeholder", _archetype_placeholder_corpus()
    )
    narr_base2 = _write_narrative_corpus(
        tmp_path / "all_placeholder2", _narrative_placeholder_corpus()
    )
    proc2 = _run_cli([
        "--json",
        "--archetype-base-path", str(arch_base2),
        "--narrative-base-path", str(narr_base2),
    ])
    # None complete -> 1
    assert proc2.returncode == 1


def test_cli_strict_requires_all_complete(tmp_path: Path) -> None:
    arch_base = _write_archetype_corpus(tmp_path, _archetype_complete_corpus())
    narr_base = _write_narrative_corpus(tmp_path, _narrative_placeholder_corpus())

    proc = _run_cli([
        "--strict",
        "--json",
        "--archetype-base-path", str(arch_base),
        "--narrative-base-path", str(narr_base),
    ])
    # One complete but not all -> --strict demands 1
    assert proc.returncode == 1

    arch_base2 = _write_archetype_corpus(tmp_path / "both", _archetype_complete_corpus())
    narr_base2 = _write_narrative_corpus(tmp_path / "both", _narrative_complete_corpus())
    proc2 = _run_cli([
        "--strict",
        "--json",
        "--archetype-base-path", str(arch_base2),
        "--narrative-base-path", str(narr_base2),
    ])
    # All complete -> 0
    assert proc2.returncode == 0


def test_cli_corpus_filter_restricts_output(tmp_path: Path) -> None:
    arch_base = _write_archetype_corpus(tmp_path, _archetype_complete_corpus())
    narr_base = _write_narrative_corpus(tmp_path, _narrative_placeholder_corpus())

    proc = _run_cli([
        "--json",
        "--corpus", "archetype_gold",
        "--archetype-base-path", str(arch_base),
        "--narrative-base-path", str(narr_base),
    ])
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert set(payload["corpora"]) == {"archetype_gold"}
    assert payload["summary"] == "1 corpora checked; 1 complete, 0 incomplete"


def test_cli_human_output_includes_verdict_lines(tmp_path: Path) -> None:
    arch_base = _write_archetype_corpus(tmp_path, _archetype_complete_corpus())
    narr_base = _write_narrative_corpus(tmp_path, _narrative_placeholder_corpus())

    proc = _run_cli([
        "--archetype-base-path", str(arch_base),
        "--narrative-base-path", str(narr_base),
    ])
    assert "[COMPLETE] archetype_gold v1" in proc.stdout
    assert "[INCOMPLETE] narrative_gold v1" in proc.stdout
    assert "2 corpora checked; 1 complete, 1 incomplete" in proc.stdout


def test_cli_unknown_corpus_via_collect_status() -> None:
    """An unknown corpus name passed to collect_status raises ValueError;
    main() catches it and exits 2."""
    try:
        collect_status(corpora=["nonexistent_gold"])
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown corpus")
