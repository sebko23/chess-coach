# CHESS COACH tests

This directory is the test suite for the chess-coach project.
**Start here** — every test file has a clear purpose and a
suggested running order.

## Test layout

| Path | Type | What it tests | Run command |
|---|---|---|---|
| `tests/integration/` | Integration tests that hit a real or in-process backend | The production code paths via real HTTP requests (smoke_test.py is end-to-end via `httpx.Client`) | `pytest tests/integration/smoke_test.py` or `python tests/integration/smoke_test.py` (standalone) |
| `tests/integration/` (others) | In-process integration tests with ASGI transport | The Phase 2-3 backend routes with mocked engines | `pytest tests/integration/` |
| `tests/unit/` | Unit tests for shared Python libraries | `libs/chess_coach/` modules in isolation | `pytest tests/unit/` |
| `tests/perf/` | Performance regression tests | The lazy eval-graph at 6000-game scale (BBF-25 regression suite) | `pytest tests/perf/ -v --durations=0` |
| `tests/gold/` | Gold evaluation data (CC-BY-4.0) | L-2 gold set: hand-verified FEN positions for board recognition (Phase 6 future) | Used by tests that read `tests/gold/*.json` |
| `tests/golden/` | Output snapshots | Test fixtures — expected outputs for backend route responses | Used by snapshot tests |
| `tests/conftest.py` | Shared pytest fixtures | Per-test isolated `CHESS_COACH_DATA_DIR` + log-level config | Imported by pytest automatically |

## Running tests

### Smoke test (recommended first run)

The smoke test hits a real running backend over HTTP and verifies
the full lazy eval-graph path. This is the most important test
for catching regressions in BBF-22's lazy architecture.

```bash
# 1. Start the backend (any of these work)
docker compose up -d                                              # Docker
uv run python -m chess_coach.gateway                              # Local venv

# 2. Wait for it to be ready
curl -sS http://127.0.0.1:18080/v1/system/health \
  -H "Authorization: Bearer devtoken123"

# 3. Run the smoke test
python tests/integration/smoke_test.py
# OK smoke_test passed: 7 positions, all with score_cp
```

The smoke test exits 0 on success and 1-4 on specific failure
modes (see the script header for the codes). It's also
parameterized for `CHESS_COACH_BASE_URL` and
`CHESS_COACH_BACKEND_TOKEN` env vars if your backend is at a
non-default address.

### pytest (unit + in-process integration)

```bash
# In-process integration: no backend needed
pytest tests/integration/ -k "not smoke"

# Unit tests
pytest tests/unit/

# All tests (slow; the perf tests are real-stockfish)
pytest tests/ --durations=0
```

### Performance regression

```bash
# BBF-25's 6000-game stress test
pytest tests/perf/ -v --durations=0
```

This is a real-Stockfish test that takes minutes to run. Don't
include it in normal dev loops; it's a CI gate.

## When you add a new test

1. **Pick the right layer**:
   - Tests that hit a real backend over HTTP → `tests/integration/smoke_test.py`
     or a new file in `tests/integration/`
   - Tests that exercise a backend route in-process → `tests/integration/`
     with the `prod_client` fixture pattern
   - Tests for a `libs/chess_coach/` module → `tests/unit/`

2. **Mock engines** for in-process tests. The `engine_client`
   fixture in `tests/integration/test_api_routes.py` is a
   template.

3. **Snapshot tests** belong in `tests/golden/`. Update the
   snapshots in the same PR as the code change that affected them.

4. **Gold set test data** belongs in `tests/gold/`. Don't
   hand-edit — if a hand-verified FEN needs to change, that's an
   investigation, not a patch.

5. **Performance tests** are real-Stockfish and slow. Add them to
   `tests/perf/` only when you have a real regression to detect.

## CI

GitHub Actions runs `tests/integration/smoke_test.py` on every
push to main and every PR (see
`../.github/workflows/smoke.yml`). The smoke workflow builds
the backend in a step and runs the smoke test against it.

In-process `pytest` tests are **not** in CI yet. That's a
follow-on sprint: `.github/workflows/lint.yml` and
`.github/workflows/test.yml`.

## History

The smoke test was added in BBF-29 (commit `e65f94c`). It
existed as a forward reference in BBF-27 docs that promised
"a more practical smoke test that exercises the lazy eval-graph
path is at `tests/integration/smoke_test.py`". Before BBF-29
existed, the smoke test was the curl `/v1/system/health` check
in `BUILDING.md` — coarse-grained and didn't exercise the
lazy path at all.

The performance tests trace back to BBF-25 (the 6000-game
stress test). Before BBF-22's lazy architecture, the perf
budget was dominated by import-time analysis, so the perf
tests had different shapes. They were rewritten in BBF-25 to
stress the lazy path instead.
