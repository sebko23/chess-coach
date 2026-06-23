# SESSION HANDOVER — 2026-06-23 (Phase 3 KB wire-up)

## Headline
Phase 3 `memory_kb` module is now wired into the gateway. The new
`POST /v1/kb/similar` and `POST /v1/kb/index` endpoints are live and
covered by 7 new integration tests (TestKB). 55/55 tests in the
regression suite pass. Two remaining Phase 3 items: persistent Qdrant
deployment and module separation.

## Commits landed (this work, 2026-06-22 → 2026-06-23)

| SHA | Subject | Files | Lines | What it does |
|---|---|---|---|---|
| `424737b` | `feat(gateway): wire memory_kb into gateway with /kb/similar route (Phase 3)` | `app.py`, `routes/__init__.py`, `routes/kb.py` (new) | +99 | `kb_router` (APIRouter prefix=`/v1/kb`) with two endpoints (similar + index); eager init of `PositionStore` in lifespan via `index_positions`; `kb_router` added to `app.py` import list and `app.include_router` calls; `kb_router` exported from `routes/__init__.py` |
| `e3a522e` | `test(kb): add TestKB integration tests for /v1/kb/similar and /v1/kb/index` | `tests/integration/test_api_routes.py` | +99 | New `TestKB` class with 7 tests: happy-path (200), validation (422), auth (401) for both endpoints, plus shape assertion on the response hits |

**Final state:** HEAD on `master` at `e3a522e`, working tree clean.

## Phase 3 remaining gaps (next session, when this phase resumes)

### 1. Persistent Qdrant deployment

Current `PositionStore` is `QdrantClient(":memory:")` — **lost on every
gateway restart**. Need:

- Qdrant container in `docker-compose.yml` (or systemd unit)
- `QDRANT_URL` + `QDRANT_API_KEY` env vars in `.env`
- Persistent volume mounted at Qdrant's data dir
- Switch the `index_positions` call to pass `persist_path=...` so the
  Qdrant client connects to the persistent instance
- `kb.py` docstring already notes the upgrade path; expand into
  `docs/03_technology/qdrant-deployment.md`

### 2. `kb` module separation from `memory`

`services/chess_coach/memory_kb/` is co-located with other service
modules under `services/chess_coach/`. The roadmap calls for a clean
module boundary. Either:

- Move to `services/chess_coach/kb/` (rename), update all imports, re-run regression
- Or promote to `services/kb/` (top-level), wire imports in `pyproject.toml`

Tradeoff: keeping under `services/chess_coach/` keeps the relative
imports short. Promoting to `services/kb/` aligns with the multi-service
architecture intent.

**Effort:** persistent Qdrant ~1–2 hr, module separation ~30 min.

## Process errors this session + the fix patterns

### Error 1: Silent no-op in `str.replace` recovery script (tool 89)

**What happened:** The first attempt to apply Blocks 1.2 and 3.1 used a
Python `str.replace` script. The anchors didn't match (whitespace
mismatch on Block 1.2; the `__all__` block had a different shape on
Block 3.1), the asserts were too weak, and the script proceeded as if
the replacement had landed. The commit went out with 2 files instead of
3, and the `kb_router` import in `app.py` was missing from the import
list — 20 integration tests errored with `NameError: name 'kb_router' is
not defined`.

**Catch:** The pytest run (post-commit) showed 20 errors, not the
expected 48/48. The error traceback pointed at line 269 of `app.py`.

**Fix pattern (now established for ALL diff-style file edits):**

```python
from pathlib import Path
p = Path('services/chess_coach/gateway/app.py')
text = p.read_text()

old = "<EXACT old text, whitespace-sensitive>"
new = "<new text>"

# 1. Anchor must exist verbatim
assert old in text, "ANCHOR FAIL — old text not found verbatim"
print(f"anchor matched exactly, length: {len(old)}")

# 2. Replacement must actually change something
text2 = text.replace(old, new, 1)
assert text2 != text, "REPLACE FAIL — text unchanged"

# 3. Post-condition: the new content is actually present
assert "<expected new content>" in text2, "POST-FAIL — <what's missing>"

p.write_text(text2)
print("OK: <change description>")
```

**Three assertions, not zero.** This is the only pattern I'll use for
diff-style file edits going forward.

### Error 2: Applied test class with nonexistent fixture

**What happened:** First apply of the `TestKB` class used
`async def test_...(self, client, auth_headers):`. Neither fixture
exists in the file. The `client` fixture comes from `tests/conftest.py`
(unused by `test_api_routes.py`), and `auth_headers` doesn't exist
anywhere — the actual pattern in this file is `prod_client` (local
fixture) + `AUTH` (module-level constant defined at line 87 of
`test_api_routes.py`).

**Catch:** pytest error `fixture 'auth_headers' not found` with the
full available-fixtures list visible.

**Fix pattern (for ALL test code that uses fixtures):**

Before writing any test class, run:

```bash
grep -n "^def <fixture_name>\|^async def <fixture_name>" \
  tests/integration/test_api_routes.py tests/conftest.py tests/integration/conftest.py 2>/dev/null
```

If the grep returns nothing, the fixture doesn't exist. Either:
- Use a different fixture that DOES exist (e.g., `prod_client` instead of `client`)
- Define the missing fixture in the test file or conftest
- Build the auth header inline (e.g., `headers={"Authorization": "Bearer devtoken123"}`)

**Never write a test class against a fixture name you haven't verified exists.**

## Test fixture pattern in `tests/integration/test_api_routes.py`

| Use case | Pattern |
|---|---|
| Test client (positive) | `async def test_...(self, prod_client):` (local fixture, line 25) |
| Auth header (positive) | `headers=AUTH` where `AUTH = {"Authorization": "Bearer devtoken123"}` is a module-level constant at line 87 |
| Auth header (negative / 401) | `headers={"Authorization": "Bearer wrong-token"}` inline |
| Global active token | autouse `_patch_env` fixture (line 17) calls `set_active_token("devtoken123")` and clears on teardown — runs for every test |
| Mocked engine pool + LLM | `async def test_...(self, engine_client):` (local fixture, line 38) |

**`auth_headers` does NOT exist anywhere in this project.** If you see
a test file using it, that's a bug — replace with `prod_client` + `AUTH`
or inline `headers=`.

## Session-start checklist (corrected, with absolute path)

```bash
cd /a0/usr/projects/chess_coach

git log --oneline -3                            # expect: e3a522e, 424737b, 21b2e02
git status --porcelain                          # expect: clean

# Memory + tools disabled-file checks
ls .a0proj/memory/ 2>/dev/null | head -5        # expect: index.pkl, knowledge_import.json, embedding.json
ls /a0/plugins/_memory/tools/memory_save.py.disabled     # expect: present
ls /a0/plugins/_office/extensions/python/tool_execute_after/_20_document_response_affordance.py.disabled  # expect: present

# Rust toolchain (one-liner — cargo/rustc are in /root/.cargo/bin, not default PATH)
export PATH="/root/.cargo/bin:$PATH"
which cargo rustc                                # expect: /root/.cargo/bin/{cargo,rustc}

# Gateway start — ABSOLUTE PATH (standing rule since early sessions)
/a0/start_gateway.sh                            # NOT a0/start_gateway.sh

# Memory + artifact baseline (verify the 1361-doc baseline)
python3 -c "
import pickle, pathlib
class _Stub:
    def __setstate__(self, s):
        if isinstance(s, dict): self.__dict__.update(s)
class _P(pickle.Unpickler):
    def find_class(self, m, n):
        try: return super().find_class(m, n)
        except: return _Stub
with open('.a0proj/memory/index.pkl', 'rb') as f:
    docs, _ = _P(f).load()
d = docs.__dict__.get('_dict', {})
print(f'docs: {len(d)}')
az = [k for k,v in d.items() if 'Agent Zero' in v.__dict__.get('__dict__', v.__dict__).get('page_content', '')]
print(f'AZ docs: {len(az)}
