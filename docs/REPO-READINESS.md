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

## Backend architecture overview

- `services/chess_coach/gateway/` — FastAPI app. The lifespan handler in `app.py` reads settings, runs migrations, sets up the engine pool, and mounts routers. Routes are in `gateway/routes/`.
- `services/chess_coach/engine_orch/pool.py` — Stockfish process pool. N slots (`CHESS_COACH_MAX_WORKERS`), per-slot asyncio.Lock. See BBF-19 for the slot design.
- `services/chess_coach/gateway/routes/eval_graph.py` — lazy eval-graph. On cache miss (LEFT JOIN finds no analyses row), runs Stockfish inline, caches, returns. See BBF-22 for the design.
- `services/chess_coach/gateway/routes/pgn_import.py` — pure-insert PGN import. See BBF-22.
- `services/chess_coach/gateway/routes/backfill_analyses.py` — explicit pre-compute. See BBF-21.
- `libs/chess_coach/storage/` — SQLite migrations, schema introspection.

## Desktop architecture overview

- `apps/desktop/src/routes/games.tsx` — games list page
- `apps/desktop/src/routes/games.$gameId.tsx` — game detail route
- `apps/desktop/src/components/panels/games/GamesPage.tsx` — games list panel (import button, backfill button)
- `apps/desktop/src/components/panels/games/GameDetailPage.tsx` — game detail panel (eval-graph, blunders, "Compute full analysis" button)
- `apps/desktop/src/bindings/` — generated TypeScript types for the v1.0.0 protocol
- `apps/desktop/src/components/panels/coach/EvalGraph.tsx` — the eval-graph SVG renderer

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
curl -sS http://127.0.0.1:18080/v1/system/health -H "Authorization: Bearer devtoken123"
curl -sS -X POST http://127.0.0.1:18080/v1/import/pgn \
  -H "Authorization: Bearer devtoken123" -H "Content-Type: application/json" \
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

The codebase is shipped with three known real bugs identified by
the BBF-34 code audit. See
[`14_adrs/ADR-0006-engine-pool-failure-modes.md`](14_adrs/ADR-0006-engine-pool-failure-modes.md)
for full details and "Current behavior" impact. Brief summary:

- **BBF-35**: Engine pool has no timeouts on Stockfish calls. A
  hung Stockfish wedges one slot. Recovery: backend restart.
  Fix planned (~15 LOC, ~1 day).
- **BBF-36**: Eval-graph concurrent-request race. Two concurrent
  requests for the same game's first view both compute (the second
  is wasted work) but the analyses-table primary key prevents
  corruption. Fix planned (~15 LOC, ~0.5 day).
- **BBF-37**: Desktop discovery hardcodes `$HOME/.local/share/...`
  on macOS and Windows. On those platforms the desktop can't find
  the backend unless `CHESS_COACH_DATA_DIR` is set explicitly in
  both shells. Fix needs Tauri env-var read + macOS/Windows
  validation.

None of these bugs are blockers for the typical Linux dev workflow.


## Sprint history

See `docs/CHANGELOG.md` for the full BBF-1..BBF-26 sprint history. The current strategic focus is repo-readiness (BBF-27 onwards); the next planned work is the 6000-game scaling follow-on (lazy eval-graph was the foundation; we're now in the polish phase).
