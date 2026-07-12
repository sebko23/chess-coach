"""Integration test: probe + gold set → metric computation end-to-end.

Stub sprint (L-2) deliverable. Future sprints: extend gold set to 50+ pages.
"""
import importlib.util
import json
import os
import sys

GOLD_SET_PATH = "/a0/usr/projects/chess_coach/tests/gold/chess_gold_set_v1.json"
SCRIPT_PATH = "/a0/usr/projects/chess_coach/scripts/pdftomd_probe.py"


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
    """End-to-end: gold set loaded, classified inputs synthesized, _compute_metrics returns non-None values."""
    spec = importlib.util.spec_from_file_location("pdftomd_probe", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
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
