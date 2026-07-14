# CHESS COACH

**Grandmaster-level autonomous chess coaching platform.**

A Python FastAPI backend (`services/`) plus a Tauri/React desktop GUI
(`apps/desktop/`, forked from [en-croissant](https://github.com/franciscoBSalgueiro/en-croissant))
that gives ground-truth Stockfish analyses and grounded coaching narration
for your chess games. The backend does no pre-compute; analyses are computed
lazily on first view and cached in the local SQLite DB.

## Quick start

You need three things: a working backend, a working desktop, and a way for
them to find each other. The desktop auto-discovers the backend via
`${CHESS_COACH_DATA_DIR}/runtime/backend.json`, so the only environment
variable you have to set is `CHESS_COACH_DATA_DIR` (any writable directory).

### Backend (Python)

```bash
# In a venv:
uv venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Optional: pin the dev token so you can curl without reading backend.json
export CHESS_COACH_BACKEND_TOKEN=devtoken123
# Optional: pin how many stockfish subprocesses to spawn (default 1).
# Set to your CPU core count for max parallelism, but each stockfish
# process spawns its own OS thread, so high values can hit the
# per-process thread limit on the host.
export CHESS_COACH_MAX_WORKERS=2
export CHESS_COACH_DATA_DIR="$HOME/.local/share/chess-coach"
mkdir -p "$CHESS_COACH_DATA_DIR"

# Drop a stockfish binary somewhere on PATH, or set stockfish_path in settings.
# The agent-zero container has it at /usr/local/bin/stockfish already.
# If you don't have one: apt install stockfish (Debian) or
# brew install stockfish (macOS), or build from source.

# Run the gateway:
python -m chess_coach.gateway
# Listens on 0.0.0.0:18080.
```

Smoke test:

```bash
curl -sS http://127.0.0.1:18080/v1/system/health \
  -H "Authorization: Bearer devtoken123"
# {"data":{"status":"ok",...}}
```

### Backend (Docker)

If you'd rather not manage a Python venv, the backend can be run in a container:

```bash
# From the repo root
docker compose build      # one-time, ~30s
docker compose up -d
docker compose logs -f backend

# Same smoke test as the venv path
curl -sS http://127.0.0.1:18080/v1/system/health \
  -H "Authorization: Bearer devtoken123"
```

The image is `python:3.11-slim-bookworm` with stockfish installed via apt. Data is bind-mounted to `./data` on the host, so the SQLite DB and `runtime/backend.json` survive restarts. See `BUILDING.md` § "Running the backend in Docker" for details.

### Desktop (Tauri/React)

```bash
cd apps/desktop
pnpm install
pnpm tauri dev          # full Tauri dev with hot reload
# or:
pnpm dev                # vite-only dev (faster, no Tauri shell)
```

The desktop reads `${CHESS_COACH_DATA_DIR}/runtime/backend.json` to find
the backend. If you started the backend with `CHESS_COACH_DATA_DIR` set,
the desktop will pick it up automatically when launched from the same
shell. To point the desktop at a remote backend, set the same env var
in the desktop's shell.

### End-to-end smoke test

After both are up, drop a small PGN into the desktop's import button.
The first time you open a game's eval-graph, analyses are computed
lazily (~1-2 s for a 50-ply game at depth 6 with 1 stockfish worker).
Subsequent views are instant (cache hit, < 100 ms).

A scripted smoke test that exercises the full lazy path lives at
`tests/integration/smoke_test.py`. Run it after starting the backend:

```bash
python tests/integration/smoke_test.py
```

## Project structure

```
chess-coach/
├── apps/
│   └── desktop/              Tauri + React + en-croissant fork (frontend)
├── services/                 Python FastAPI monolith (backend gateway)
├── libs/                     Python libs (storage, engine_orch, narration, kb, etc.)
├── docs/                     Architecture, design notes, sprint results
│   ├── 14_adrs/              Architecture Decision Records
│   ├── 17_lazy_eval_graph/   BBF-22 strategic pivot spec + 6000-game stress results
│   ├── REPO-READINESS.md     Operational guide for new developers
│   └── CHANGELOG.md          Sprint history (BBF-1 through current)
├── specs/                    Protocol v1.0.0 spec (CC-BY-4.0)
├── tests/
│   ├── gold/                 L-2 gold set (PDF→FEN eval data)
│   └── integration/          End-to-end smoke tests
├── scripts/                  One-off operational scripts
├── tools/                    Internal tooling
└── infra/                    Installer / packaging configs
```

## What is where

- **`services/chess_coach/gateway/`** — FastAPI app. Routes: `/v1/games`,
  `/v1/import/pgn`, `/v1/import/backfill-analyses`, `/v1/engines`,
  `/v1/system/health`, etc. See `apps/desktop/openapi.json` for the
  full contract.
- **`services/chess_coach/engine_orch/pool.py`** — Stockfish process
  pool with N slots (`CHESS_COACH_MAX_WORKERS`). Per-slot asyncio.Lock
  prevents concurrent reads on the same Stockfish subprocess.
- **`services/chess_coach/gateway/routes/eval_graph.py`** — lazy
  eval-graph. On cache miss, computes analyses inline, caches them
  in the `analyses` table. See `docs/17_lazy_eval_graph/SPEC.md` for
  the design and the perf curve.
- **`apps/desktop/src/components/panels/games/`** — Games list and
  detail pages. The detail page has a "Compute full analysis" button
  (BBF-24) for pre-warming the cache at a chosen depth.

## Contributing

See `CONTRIBUTING.md` for the workflow. Quick version: the frontend is
a fork of en-croissant, so any upstream en-croissant changes need a
`git subtree pull` from the SHA in `.upstream-ref` (see
`CONTRIBUTING.md` § "Frontend fork"). The backend is original work.

## Licensing

See `LICENSING.md` — the GUI is GPL-3.0-only (fork of en-croissant), the
backend is Apache-2.0, the protocol spec is CC-BY-4.0.

## Status

Phase 5 — Repertoire + Training: 85%. Phase 6 — PDF/Vision: not started
in this repo. The strategic pivot to lazy eval-graph (BBF-22) is
verified at 6000-game scale (BBF-25): 43.8 s import, ~1 s first-eval
per game, instant cache hits. See `docs/CHANGELOG.md` for the full
sprint history.
