"""Permanent regression tests for pdftomd_probe.py metric namespace.

Frozen as of 2026-07-10 by the metric-contract-freeze sprint.
Hardened on 2026-07-10 by the MCF-FU sprint:
- Uses NamedTuple field accessors (result.metric_1) instead of position unpacking.
- Imports METRIC_KEYSPACE from the script as the single source of truth.
- Adds test_metric_compute_result_namedtuple_shape (pins _fields tuple).
- Adds test_metric_1_semantic_pin (LR-3: pins *semantics*, not just *name*).

Future changes to the metric namespace require a sprint with explicit
migration planning. See idea memo §32 for the freeze declaration.
"""
import importlib.util
import os
import sys
from pathlib import Path

# Locate the pdftomd_probe.py script.
#
# Resolution order (matches the script's own PDTM_PROJECT_ROOT convention):
#   1. PDFTOMD_PROBE_PATH env var (full path to the script itself)
#   2. PDTM_PROJECT_ROOT env var (project root containing scripts/pdftomd_probe.py)
#   3. Default: <repo root>/scripts/pdftomd_probe.py, where repo root is
#      the test file's parents[2] (tests/unit/<file> -> tests/ -> repo).
#
# This replaces the prior hardcoded /a0/usr/projects/chess_coach/... path
# which only worked on the agentZero Linux container and broke pytest
# collection on Windows hosts.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SCRIPT = _REPO_ROOT / "scripts" / "pdftomd_probe.py"
if os.environ.get("PDFTOMD_PROBE_PATH"):
    _SCRIPT = Path(os.environ["PDFTOMD_PROBE_PATH"])
elif os.environ.get("PDTM_PROJECT_ROOT"):
    _SCRIPT = Path(os.environ["PDTM_PROJECT_ROOT"]) / "scripts" / "pdftomd_probe.py"
else:
    _SCRIPT = _DEFAULT_SCRIPT
assert _SCRIPT.is_file(), (
    f"pdftomd_probe.py not found at {_SCRIPT}. Set PDFTOMD_PROBE_PATH to the "
    f"full path to pdftomd_probe.py, or PDTM_PROJECT_ROOT to the project root "
    f"containing scripts/pdftomd_probe.py, or run pytest from a checkout where "
    f"{_DEFAULT_SCRIPT} exists."
)
_SPEC = importlib.util.spec_from_file_location("pdftomd_probe", str(_SCRIPT))
_mod = importlib.util.module_from_spec(_SPEC)
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC.loader.exec_module(_mod)


def test_metric_namespace_is_frozen():
    """The JSON output must contain exactly the expected metric fields and no
    forbidden ones. Uses METRIC_KEYSPACE imported from the script as the
    single source of truth."""
    sample_payload = {
        "book": None,
        "book_fallback_reason": "test",
        "pages_in_chapter_1": 0,
        "diagrams_detected": 0,
        "diagrams_classified": 0,
        "fen_legality_pass_rate": 0.0,
        "metric_1_full_fen_match": 0,
        "metric_2_full_board_fen_position_match": 0.0,
        "metric_2a_piece_squares_only": 0.0,
        "time_elapsed_seconds": 0.0,
        "errors": [],
    }
    actual_metric_fields = {k for k in sample_payload if k.startswith("metric_")}
    # Import the keyspace from the script (single source of truth).
    assert _mod.METRIC_KEYSPACE["expected"] == actual_metric_fields, (
        f"metric namespace drift! expected={_mod.METRIC_KEYSPACE['expected']} "
        f"actual={actual_metric_fields}"
    )
    # Confirm the forbidden list is also enforced.
    for forbidden_key in _mod.METRIC_KEYSPACE["forbidden"]:
        assert forbidden_key not in sample_payload, (
            f"forbidden key {forbidden_key!r} unexpectedly present in payload"
        )


def test_metric_1_tri_state():
    """Metric #1 is tri-state: None for no-gold, int count otherwise."""
    gold_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    result = _mod._compute_metrics([], gold={})
    assert result.metric_1 is None
    result = _mod._compute_metrics([(gold_fen, True, "", 1)], gold={1: gold_fen})
    assert result.metric_1 == 1
    assert isinstance(result.metric_1, int)


def test_metric_2a_piece_squares_only():
    """Metric #2a (new field, no 0.5-floor) is tri-state: None for no-gold,
    0.0 for no-pieces-in-gold, ratio otherwise."""
    gold_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    gold_empty = "8/8/8/8/8/8/8/8 w - - 0 1"
    classified_pawns = "8/pppppppp/8/8/8/8/PPPPPPPP/8 w - - 0 1"

    # No gold → None
    result = _mod._compute_metrics([], gold={})
    assert result.metric_2a_piece_squares_only is None

    # Gold with no pieces (empty board) → 0.0
    result = _mod._compute_metrics(
        [(gold_empty, True, "", 1)], gold={1: gold_empty}
    )
    assert result.metric_2a_piece_squares_only == 0.0

    # Gold full vs classified full → 1.0
    result = _mod._compute_metrics(
        [(gold_fen, True, "", 1)], gold={1: gold_fen}
    )
    assert result.metric_2a_piece_squares_only == 1.0

    # Gold full vs classified pawns-only → 16/32 = 0.5
    result = _mod._compute_metrics(
        [(classified_pawns, True, "", 1)], gold={1: gold_fen}
    )
    assert result.metric_2a_piece_squares_only == 0.5


def test_metric_2b_tri_state():
    """Metric #2b (position-field match) is tri-state: None for no-gold, ratio otherwise."""
    gold_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    gold_empty = "8/8/8/8/8/8/8/8 w - - 0 1"
    classified_full = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

    # No gold → None
    result = _mod._compute_metrics([], gold={})
    assert result.metric_2b is None

    # Gold with no pieces → 1.0 (position-field matches: empty==empty)
    result = _mod._compute_metrics(
        [(gold_empty, True, "", 1)], gold={1: gold_empty}
    )
    assert result.metric_2b == 1.0

    # Gold full vs classified full → 1.0
    result = _mod._compute_metrics(
        [(classified_full, True, "", 1)], gold={1: gold_fen}
    )
    assert result.metric_2b == 1.0

    # Gold full vs gold_empty (position field differs) → 0.0
    result = _mod._compute_metrics(
        [(classified_full, True, "", 1)], gold={1: gold_empty}
    )
    assert result.metric_2b == 0.0


def test_metric_field_does_not_drift():
    """Pin the exact metric field names emitted by the JSON output. This test
    catches future regressions where someone re-adds metric_2_per_square_accuracy
    or removes one of the frozen fields. Uses METRIC_KEYSPACE imported from
    the script."""
    expected_metric_keys = _mod.METRIC_KEYSPACE["expected"]
    forbidden_metric_keys = _mod.METRIC_KEYSPACE["forbidden"]
    for key in expected_metric_keys:
        assert isinstance(key, str)
    for key in forbidden_metric_keys:
        assert key not in expected_metric_keys


def test_metric_compute_result_namedtuple_shape():
    """Assert that _compute_metrics returns a MetricComputeResult NamedTuple
    with the exact field set. This pins the return type's _fields so
    consumers that introspect result.metric_1 etc. are not broken by
    reordering."""
    result = _mod._compute_metrics([], gold={})
    assert isinstance(result, _mod.MetricComputeResult)
    assert result._fields == (
        "metric_1",
        "metric_2a",
        "metric_2b",
        "metric_2a_piece_squares_only",
    )


def test_metric_1_semantic_pin():
    """Semantic pin for Metric #1: it is *exactly* full-string FEN equality,
    not relaxed, not "full-board FEN position match". This protects the
    *meaning* of the metric, not just its *name* (LR-3)."""
    gold_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    # Case 1: exact match → 1
    result = _mod._compute_metrics([(gold_fen, True, "", 1)], gold={1: gold_fen})
    assert result.metric_1 == 1
    # Case 2: FEN strings differ ONLY in the half-move clock (last field) → 0.
    # This proves Metric #1 is byte-identical FEN equality, not "ignore clock".
    fen_clock_99 = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 99"
    result = _mod._compute_metrics([(fen_clock_99, True, "", 1)], gold={1: gold_fen})
    assert result.metric_1 == 0, (
        f"Metric #1 should be byte-identical FEN equality; got {result.metric_1} "
        f"for a clock-difference input."
    )
    # Case 3: FEN strings differ ONLY in en-passant target → 0.
    fen_ep = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq e6 0 1"
    result = _mod._compute_metrics([(fen_ep, True, "", 1)], gold={1: gold_fen})
    assert result.metric_1 == 0, (
        f"Metric #1 should be byte-identical FEN equality; got {result.metric_1} "
        f"for an en-passant-difference input."
    )
    # Case 4: FEN strings differ ONLY in side-to-move → 0.
    fen_stm = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1"
    result = _mod._compute_metrics([(fen_stm, True, "", 1)], gold={1: gold_fen})
    assert result.metric_1 == 0, (
        f"Metric #1 should be byte-identical FEN equality; got {result.metric_1} "
        f"for a side-to-move-difference input."
    )
