# Repo-Readiness Guide

This document is the operational guide for "I just cloned this repo, what do I do?" — covering the two runtimes, the binding between them, the smoke tests, the common pitfalls, and how to get a working dev environment end-to-end.

## TL;DR for a new dev

```bash
# 1. Backend (in a venv)
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
export CHESS_COACH_BACKEND_TOKEN=devtoken123
export CHESS_COACH_MAX_WORKERS=2
python -m chess_coach.gateway

# 2. Desktop (in another terminal)
cd apps/desktop
pnpm install
pnpm tauri dev

# 3. Smoke test
python tests/integration/smoke_test.py
```

If all three steps succeed, you have a working chess-coach dev environment. If any step fails, see "Pitfalls" below.

## The two runtimes

CHESS COACH has two independent codebases that communicate over HTTP:

1. **Backend** (Python FastAPI monolith, `services/chess_coach/`)
   - Single Python process: `python -m chess_coach.gateway`
   - Listens on `0.0.0.0:18080` by default
   - Owns the SQLite database, the Stockfish process pool, the KB / Qdrant connection
   - Doesn't depend on anything else in the repo. You can run it standalone.

2. **Desktop** (Tauri + React + en-croissant fork, `apps/desktop/`)
   - Tauri shell + Vite dev server
   - Calls the backend over HTTP using the v1.0.0 protocol
   - Finds the backend via `${CHESS_COACH_DATA_DIR}/runtime/backend.json`
   - Doesn't depend on the backend being in the same directory; just needs the descriptor file

The binding is the `backend.json` descriptor file. The backend writes it on startup, the desktop reads it on startup. The descriptor contains:

```json
{
  "backend_version": "0.1.0",
  "host": "127.0.0.1",
  "port": 18080,
  "protocol_version": "1.0.0",
  "session_token": "..."
}
```

`session_token` is the bearer token. The desktop reads it from the file and uses it for every request. If you set `CHESS_COACH_BACKEND_TOKEN=devtoken123` in the backend's env, the descriptor's `session_token` will be `devtoken123` and you can curl with the same.

## Pitfalls

These are the things that will eat your day if you don't know about them. The fixes are documented; the goal of this section is to make sure you find them within 5 minutes instead of 2 hours.

### "curl returns 401"

The bearer token doesn't match. Either:
- You didn't set `CHESS_COACH_BACKEND_TOKEN=devtoken123` in the backend's env, and the gateway auto-generated a random token. Read the real token from `${CHESS_COACH_DATA_DIR}/runtime/backend.json`.
- You set it in a different shell than the gateway is running in. `echo $CHESS_COACH_BACKEND_TOKEN` in the gateway's shell.

### "curl returns 404 on /v1/import/pgn"

The frontend (pre-BBF-26) was calling `/v1/import/pgn-database` which is not a real route. If you're seeing this in code, search the frontend for `pgn-database` and replace with `pgn`. The backend has only `/v1/import/pgn` and `/v1/import/backfill-analyses`.

### "Gateway starts, dies after a few requests with `can't start new thread`"

This is the BBF-22 "thread limit" failure (see `docs/17_lazy_eval_graph/RESULTS.md`). It's a per-process thread limit on the host, not a chess-coach bug. Fixes:
- Reduce `CHESS_COACH_MAX_WORKERS` to 1 or 2
- Restart the gateway
- If running in a container, restart the container (`docker restart <name>`)

### "First eval-graph call returns 7/19 positions, then 0 results"

Same root cause as above — the host killed the gateway mid-request. The cgroup wedge is most common in agentZero containers. Run `docker restart <container>` and re-test.

### "PGN import hangs at 30s with HTTP 000"

The old (pre-BBF-22) `pgn_import.py` would block on stockfish analysis for every ply. The current code is fast (~0.3s for a single game). If you see the old behavior, your tree is pre-BBF-22. Pull the latest `main`.

### "Pip install fails with `error: subprocess-exited-with-error`"

You need a system dependency for one of the Python libs. The most common is `python3-dev` / `libpython3-dev` (for the `lxml` build). On Debian/Ubuntu: `sudo apt install build-essential python3-dev libxml2-dev libxslt1-dev`. On macOS: `xcode-select --install`.

### "Frontend won't build, `tsgo` not found"

The desktop uses `tsgo` (TypeScript Go native compiler), not `tsc`. It's in the dev dependencies. Run `pnpm install` from `apps/desktop/` and it should be available via `pnpm exec tsgo`.

### "`pnpm tauri dev` fails on Linux with `webkit2gtk-4.1` not found"

Install the Tauri Linux prereqs:
```bash
sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

### "Smoke CI workflow goes red on a fresh push"

Two pre-flight checks before debugging the actual error:

1. The `gateway-boot` job in the smoke workflow runs the boot
   regression test in a fresh venv. If it fails, the runtime
   has a missing declared dep -- check `pyproject.toml`'s
   `[project.dependencies]` against the route modules
   (and any framework-driven implicit deps like
   `python-multipart` for FastAPI `File`/`UploadFile`).
2. The `smoke` job has step 7 (Wait for backend, 120s
   curl-poll), step 8 (Run smoke test). If step 7 fails
   the container exited on startup; read the backend
   logs in step 9. If step 8 fails, read the test
   output directly.

The CI hardening for the missing-dep cascade is what
catches the "I forgot to declare X" class of bug
before it ships.

## Backend architecture overview

- `services/chess_coach/gateway/` -- FastAPI app. The lifespan handler in `app.py` reads settings, runs migrations, sets up the engine pool, and mounts routers. Routes are in `gateway/routes/`.
- `services/chess_coach/engine_orch/pool.py` -- Stockfish process pool. N slots (`CHESS_COACH_MAX_WORKERS`), per-slot asyncio.Lock, engine.go() bounded by `_engine_go_timeout_s` (default 30s, BBF-35). See BBF-19 for the slot design and BBF-35 for the timeout.
- `services/chess_coach/gateway/routes/eval_graph.py` -- lazy eval-graph. On cache miss (LEFT JOIN finds no analyses row), runs Stockfish inline, caches, returns. Concurrent first-viewers on the same `(game_id, ply, engine_id, depth)` key are coalesced via `_coalesce_analyze` (BBF-36). See BBF-22 for the lazy design.
- `services/chess_coach/gateway/routes/pgn_import.py` -- pure-insert PGN import. See BBF-22.
- `services/chess_coach/gateway/routes/backfill_analyses.py` -- explicit pre-compute. See BBF-21.
- `libs/chess_coach/storage/` -- SQLite migrations, schema introspection.

## Desktop architecture overview

- `apps/desktop/src/routes/games.tsx` -- games list page
- `apps/desktop/src/routes/games.$gameId.tsx` -- game detail route
- `apps/desktop/src/components/panels/games/GamesPage.tsx` -- games list panel (import button, backfill button)
- `apps/desktop/src/components/panels/games/GameDetailPage.tsx` -- game detail panel (eval-graph, blunders, "Compute full analysis" button)
- `apps/desktop/src/bindings/` -- generated TypeScript types for the v1.0.0 protocol
- `apps/desktop/src/components/panels/coach/EvalGraph.tsx` -- the eval-graph SVG renderer

## Common operations

### Run only the backend (no desktop)

You can develop backend features without running the desktop at all. Use `curl` for everything:

```bash
# Set up
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
export CHESS_COACH_BACKEND_TOKEN=devtoken123
export CHESS_COACH_MAX_WORKERS=2

# Start
python -m chess_coach.gateway

# Curl
curl -sS http://127.0.0.1:18080/v1/system/health -H "Authorization: Bearer ***"
curl -sS -X POST http://127.0.0.1:18080/v1/import/pgn \
  -H "Authorization: Bearer ***" -H "Content-Type: application/json" \
  -d @my_test_pgn.json
curl -sS http://127.0.0.1:18080/v1/games | head -c 500
```

### Run the smoke test

```bash
python tests/integration/smoke_test.py
```

The smoke test:
1. Calls `/v1/system/health` to confirm the gateway is up
2. Imports a 5-ply PGN
3. Fetches the eval-graph
4. Verifies all positions have `score_cp` populated

Exits 0 on success, non-zero on failure.

### Inspect the SQLite DB directly

```bash
sqlite3 ${CHESS_COACH_DATA_DIR}/sqlite/chess_coach.db
sqlite> .tables
sqlite> .schema positions
sqlite> .schema analyses
sqlite> SELECT COUNT(*) FROM games;
sqlite> SELECT COUNT(*) FROM positions;
sqlite> SELECT COUNT(*) FROM analyses;
```

### Restart everything from scratch

```bash
# Stop the gateway (Ctrl-C in its terminal)
# Wipe the data dir
rm -rf ${CHESS_COACH_DATA_DIR}
# Restart the gateway; it will recreate the DB and run migrations
```

## Known issues (BBF-34 audit, 2026-07-14)

The BBF-34 code audit identified three real bugs and one
benign race. Status as of `5ae4ca7` (head of main):

- **BBF-35**: Engine pool had no timeouts on Stockfish
  calls. A hung Stockfish wedged one slot forever, and a
  subprocess that died between requests was silently
  reused as a dead Popen. **Fixed in `24bbb1c`**
  (BBF-35, engine go timeout + dead-pid reset).
  See `services/chess_coach/engine_orch/pool.py`.
- **BBF-36**: Eval-graph concurrent-request race. Two
  concurrent first-viewers for the same `(game_id, ply,
  engine_id, depth)` cache key both computed Stockfish
  work. **Fixed in `e69fb0c`** (BBF-36, coalesce
  concurrent first-viewers). The helper lives in
  `services/chess_coach/gateway/routes/eval_graph.py`
  (`_coalesce_analyze`); tests in
  `tests/unit/test_eval_graph_dedup.py`.
- **BBF-37**: Desktop discovery hardcodes
  `$HOME/.local/share/...` on macOS and Windows. **Deferred
  indefinitely** -- needs macOS hardware to verify the
  macOS leg, and the user has no current path to that
  hardware. On Windows the fix is also blocked on a Tauri
  env-var read path that has not been prioritised.
  Linux dev workflow is unaffected (Linux is the only
  CI platform).
- The benign race (ADR-0006 Finding 4) is documented in
  the ADR but requires no fix -- the analyses table's
  `INSERT OR IGNORE` already prevents corruption.

None of the open items are blockers for the typical
Linux dev workflow. The next planned strategic work
after this BBF-47 docs catchup is the "where does
chess-coach go next" take-stock session (per the
2026-07-14 handoff).


## Sprint history

See `docs/CHANGELOG.md` for the full BBF-1..BBF-47 sprint history. The post-BBF-34 work (BBF-35..BBF-47) closed the three real bugs from the BBF-34 code audit, fixed the smoke CI workflow that had been red since BBF-32 (the missing-dep cascade was a real one -- 5 separate deps were never declared in `pyproject.toml`), and added CI hardening (a `gateway-boot` job that runs the boot regression test in a fresh venv on every push). The current strategic focus is "where does chess-coach go next" (the take-stock session listed as the next planned work in the 2026-07-14 handoff).
