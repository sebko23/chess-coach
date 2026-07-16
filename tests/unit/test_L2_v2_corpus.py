import pytest

from tests.gold.L2 import load_corpus, schema_version

def test_v1_corpus_loads_as_v1():
    corpus = load_corpus('v1')
    assert schema_version(corpus) == '1.0'
    assert len(corpus) == 12

def test_v1_corpus_entries_have_required_fields():
    corpus = load_corpus('v1')
    required = {'id', 'fen', 'phase', 'best_move_uci', 'score_cp', 'source', 'engine', 'tags'}
    for entry in corpus:
        missing = required - entry.keys()
        assert not missing


def test_v1_corpus_is_dict_when_wrapped():
    import pathlib, json
    path = pathlib.Path('tests/gold/L2/v1/corpus.json')
    raw = json.loads(path.read_text())
    assert 'schema_version' in raw and raw['schema_version'] == '2.0'
    assert 'positions' in raw and len(raw['positions']) == 12

def test_v1_positions_have_eval_deltas_after_bbf63():
    corpus = load_corpus("v1")
    for entry in corpus:
        assert "eval_deltas" in entry, f"{entry['id']} missing eval_deltas after BBF-63.4"
        assert isinstance(entry["eval_deltas"], list)
        assert len(entry["eval_deltas"]) >= 1
        # best move stays best (delta 0)
        assert entry["eval_deltas"][0]["delta_cp"] == 0

def test_v2_corpus_loads_as_v2():
    # After BBF-63.5, v2/corpus.json exists as a separate file.
    corpus = load_corpus("v2")
    assert isinstance(corpus, list)
    assert len(corpus) >= 18, f"v2 corpus has {len(corpus)} entries, expected >= 18"

def test_v2_corpus_phase_distribution_is_balanced():
    corpus = load_corpus("v2")
    counts = {p: sum(1 for x in corpus if x["phase"] == p) for p in ("opening", "middlegame", "endgame")}
    assert all(c >= 3 for c in counts.values()), counts

def test_v2_all_entries_have_eval_deltas():
    corpus = load_corpus("v2")
    no_eval = [x["id"] for x in corpus if not x.get("eval_deltas")]
    assert no_eval == [], f"v2 entries missing eval_deltas: {no_eval}"

def test_v2_all_entries_have_required_fields():
    corpus = load_corpus("v2")
    required = {"id", "fen", "phase", "best_move_uci", "score_cp", "source", "engine", "eval_deltas", "tags"}
    for entry in corpus:
        missing = required - entry.keys()
        assert not missing, f"{entry['id']} missing {missing}"

def test_v2_eval_deltas_delta_invariant():
    corpus = load_corpus("v2")
    for entry in corpus:
        d0 = entry["eval_deltas"][0]
        assert d0["move_uci"] == entry["best_move_uci"], f"{entry['id']} best_move_uci mismatch"
        assert d0["delta_cp"] == 0

def test_v2_has_at_least_1_negative_and_1_positive_outlier():
    corpus = load_corpus("v2")
    neg = [x for x in corpus if x["score_cp"] < -50]
    pos = [x for x in corpus if x["score_cp"] > 200]
    assert neg, "v2 must include at least 1 losing-error position for eval-delta interest"
    assert pos, "v2 must include at least 1 winning position (>200 cp) for eval-delta spread"
