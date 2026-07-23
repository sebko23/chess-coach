"""Integration test: probe + gold set → metric computation end-to-end.

Stub sprint (L-2) deliverable. Future sprints: extend gold set to 50+ pages.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

# Locate the gold set and probe script using the same resolver pattern as
# tests/unit/test_pdftomd_metrics.py (BBF-77 portability fix).
#
# Resolution order:
#   1. PDFTOMD_GOLD_SET_PATH env var (full path to the gold set JSON)
#   2. PDTM_PROJECT_ROOT env var (project root containing tests/gold/...)
#   3. Default: <repo root>/tests/gold/chess_gold_set_v1.json (where
#      repo root is the test file's parents[2]).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_GOLD_SET = _REPO_ROOT / "tests" / "gold" / "chess_gold_set_v1.json"
_DEFAULT_SCRIPT = _REPO_ROOT / "scripts" / "pdftomd_probe.py"
GOLD_SET_PATH = os.environ.get("PDFTOMD_GOLD_SET_PATH") or str(
    Path(os.environ.get("PDTM_PROJECT_ROOT", str(_REPO_ROOT)))
    / "tests" / "gold" / "chess_gold_set_v1.json"
)
SCRIPT_PATH = os.environ.get("PDFTOMD_PROBE_PATH") or str(
    Path(os.environ.get("PDTM_PROJECT_ROOT", str(_REPO_ROOT)))
    / "scripts" / "pdftomd_probe.py"
)


def load_gold_set():
    with open(GOLD_SET_PATH, encoding="utf-8") as f:
        gold_strs = json.load(f)
    return {int(k): v for k, v in gold_strs.items()}


def test_gold_set_is_loadable():
    gold = load_gold_set()
    assert len(gold) >= 5, f"gold set has {len(gold)} entries; need at least 5"
    for page_num, fen in gold.items():
        # Each FEN has 6 space-separated fields.
        assert len(fen.split()) == 6, f"FEN for page {page_num} malformed: {fen!r}"


def test_probe_computes_metrics_against_gold():
    """End-to-end: gold set loaded, classified inputs synthesized,
    _compute_metrics returns non-None values."""
    spec = importlib.util.spec_from_file_location("pdftomd_probe", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(SCRIPT_PATH).parent))
    spec.loader.exec_module(mod)

    gold = load_gold_set()
    # Construct synthetic classified inputs: each gold page classified IDENTICALLY to gold.
    classified = [(fen, True, "", page) for page, fen in gold.items()]
    m1, m2a, m2b, m2a_pso = mod._compute_metrics(classified, gold=gold)
    # Perfect classification → all 1.0 (m1 should equal len(gold))
    assert m1 == len(gold), f"Metric #1 expected {len(gold)}, got {m1}"
    assert m2a == 1.0, f"Metric #2a expected 1.0, got {m2a}"
    assert m2b == 1.0, f"Metric #2b expected 1.0, got {m2b}"


def test_probe_computes_metrics_with_one_wrong():
    """One wrong classification → Metric #1 should drop, others proportional."""
    spec = importlib.util.spec_from_file_location("pdftomd_probe", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(SCRIPT_PATH).parent))
    spec.loader.exec_module(mod)

    gold = load_gold_set()
    # First page classified correctly; second page classified as empty (wrong).
    first_page = next(iter(gold))
    first_fen = gold[first_page]
    second_page = next(p for p in gold if p != first_page)
    second_fen = gold[second_page]
    classified = [
        (first_fen, True, "", first_page),
        ("8/8/8/8/8/8/8/8 w - - 0 1", True, "", second_page),
    ]
    gold_subset = {first_page: first_fen, second_page: second_fen}
    m1, m2a, m2b, m2a_pso = mod._compute_metrics(classified, gold=gold_subset)
    assert m1 == 1, f"Metric #1 expected 1 (one match), got {m1}"
