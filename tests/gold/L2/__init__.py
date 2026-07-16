from __future__ import annotations

import json
from pathlib import Path

CORPUS_DIR = Path(__file__).parent

def load_corpus(version: str = 'v1') -> list[dict]:
    path = CORPUS_DIR / version / 'corpus.json'
    data = json.loads(path.read_text())
    if isinstance(data, dict) and 'positions' in data:
        return data['positions']
    return data

def schema_version(corpus_or_path) -> str:
    if isinstance(corpus_or_path, (str, Path)):
        raw = json.loads(Path(corpus_or_path).read_text())
        if isinstance(raw, dict) and 'schema_version' in raw:
            return raw['schema_version']
    return '1.0'
