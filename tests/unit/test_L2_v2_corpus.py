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

@pytest.mark.xfail(reason='v2 corpus lands in BBF-63 Tasks 4-5', strict=False)
def test_v2_corpus_loads_as_v2_after_migration():
    corpus = load_corpus('v2')
    assert schema_version(corpus) >= '2.0'
    assert len(corpus) >= 30

def test_v1_corpus_is_dict_when_wrapped():
    import pathlib, json
    path = pathlib.Path('tests/gold/L2/v1/corpus.json')
    raw = json.loads(path.read_text())
    assert 'schema_version' in raw and raw['schema_version'] == '1.0'
    assert 'positions' in raw and len(raw['positions']) == 12
