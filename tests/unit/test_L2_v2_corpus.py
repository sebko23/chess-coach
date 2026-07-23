
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
    import json
    import pathlib
    path = pathlib.Path('tests/gold/L2/v1/corpus.json')
    raw = json.loads(path.read_text())
    assert 'schema_version' in raw
    assert raw['schema_version'] == '2.0'
    assert 'positions' in raw
    assert len(raw['positions']) == 12

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
    counts = {
        p: sum(1 for x in corpus if x["phase"] == p)
        for p in ("opening", "middlegame", "endgame")
    }
    assert all(c >= 3 for c in counts.values()), counts

def test_v2_all_entries_have_eval_deltas():
    corpus = load_corpus("v2")
    no_eval = [x["id"] for x in corpus if not x.get("eval_deltas")]
    assert no_eval == [], f"v2 entries missing eval_deltas: {no_eval}"

def test_v2_all_entries_have_required_fields():
    corpus = load_corpus("v2")
    required = {
        "id", "fen", "phase", "best_move_uci", "score_cp", "source",
        "engine", "eval_deltas", "tags",
    }
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

def test_gm_positions_have_pgn_game_ids():
    import json
    import pathlib
    corpus = load_corpus("v2")
    gm_positions = [p for p in corpus if p["source"]["type"] == "gm_game"]
    for entry in gm_positions:
        assert "pgn_game_id" in entry, f"{entry['id']} missing pgn_game_id"
    game_ids = {e["pgn_game_id"] for e in gm_positions}
    labels_path = pathlib.Path("tests/gold/L2/v2/game_labels.jsonl")
    assert labels_path.exists(), "game_labels.jsonl not yet created"
    with open(labels_path) as f_label:
        labels = {json.loads(line)["pgn_game_id"] for line in f_label if line.strip()}
    assert game_ids.issubset(labels), f"Labels missing for: {game_ids - labels}"


def test_game_labels_jsonl_has_required_fields():
    import json
    required = {"pgn_game_id", "white", "black", "event", "year", "round", "result", "eco"}
    with open("tests/gold/L2/v2/game_labels.jsonl") as f_labels:
        for line in f_labels:
            if not line.strip():
                continue
            label = json.loads(line)
            missing = required - label.keys()
            assert not missing, f"Label {label.get('pgn_game_id')} missing {missing}"
