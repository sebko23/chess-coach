# CHESS COACH

**Grandmaster-level autonomous chess coaching platform.**

A Python FastAPI backend (`services/`) plus a Tauri/React desktop GUI
(`apps/desktop/`, forked from [en-croissant](https://github.com/franciscoBSalgueiro/en-croissant))
that gives ground-truth Stockfish analyses and grounded coaching narration
for your chess games. The backend does no pre-compute; analyses are computed
lazily on first view and cached in the local SQLite DB.

## Who is this for?

CHESS COACH is a chess game analysis tool, not a chess engine. It
binds a Stockfish binary to a self-hosted FastAPI backend so you can
get ground-truth engine evaluations of your games, plus grounded
narration (when the LLM is wired up).

Concrete audiences:

- **Club players (1400-2200 ELO)** who want structured feedback on
  their own games without paying for a subscription. The target
  use case is "import a tournament game, get a per-ply eval-graph
  and a list of blunders/mistakes/inaccuracies."
- **Coaches** who want to analyze a student's games offline. The
  desktop + backend pair run on one machine; no data leaves your
  network.
- **Engine nerds** who want to inspect Stockfish's behavior on
  specific positions. The eval-graph endpoint is just
  `GET /v1/games/{id}/eval-graph?depth=N`; you can curl it.

CHESS COACH is **not**:

- A chess engine (it shells out to Stockfish or another UCI engine).
- A database of master games (it's a local-first analyzer for YOUR
  games).
- A cloud service. Self-hosting is the only deployment model.

## Supported platforms

| Component | Linux | Windows | macOS |
|----------|-------|---------|-------|
| Backend  | Supported (CI-tested) | Experimental | Experimental |
| Desktop  | Supported (CI-tested) | Experimental | Experimental |
| Smoke CI | ubuntu-latest only | -- | -- |

**Primary target: Linux.** Development, CI, and the verified happy
path all run on Linux. The backend boots cleanly on a stock
Debian/Ubuntu box with the dependencies in `pyproject.toml`.

**Windows and macOS are experimental today, may change with
Phase 8.** They may work with manual `CHESS_COACH_DATA_DIR`
configuration, but they are not CI-tested and not in the
roadmap until Phase 8 (packaging). On Windows/macOS, the
backend and the desktop use different default paths for
`CHESS_COACH_DATA_DIR`:

  - Linux: `~/.local/share/chess-coach` (XDG default)
  - macOS:  `~/Library/Application Support/chess-coach`
  - Windows: `%LOCALAPPDATA%\chess-coach`

If you are running on Windows or macOS, set
`CHESS_COACH_DATA_DIR` to the same path in **both** the
backend's shell and the desktop's shell so they find each
other. Without that, the desktop cannot discover the
backend's `runtime/backend.json` and will fail to start.
The Windows path is a known deferred item (BBF-37); the
macOS path needs hardware the maintainers do not currently
have, so a verification pass is pending.

For more detail on configuring Windows/macOS (with example
env-var values per OS), see `docs/REPO-READINESS.md`
"Supported platforms".

## Architecture in 60 seconds

```
                  Desktop (Tauri + React)
                  apps/desktop/
                       |
                       | HTTP (Bearer token from backend.json)
                       v
                  Backend (FastAPI gateway)
                  services/chess_coach/
                       |
        +--------------+--------------+
        |              |              |
        v              v              v
   engine_orch     storage       narration
   (libs/)         (libs/)        (libs/)
        |              |
        v              v
   Stockfish        SQLite (analyses, positions,
   subprocess       games tables)
   pool (N slots)
```

**The flow in one line:** Desktop sends HTTP to backend -> backend
asks engine_orch to run a Stockfish analysis -> engine_orch
returns the analysis -> backend writes it to SQLite -> desktop
displays the eval graph.

**Key boundary:** the engine pool is the only thing that talks to
Stockfish. Everything else -- the gateway, the storage layer, the
desktop -- talks to engine_orch via an `AnalysisRequest` /
`AnalysisResult` interface. Replacing Stockfish with leela-zero
or another UCI engine is a one-file change to
`services/chess_coach/engine_orch/pool.py`.

**Lazy evaluation:** the import path inserts games and positions
only. Analyses are computed on the first
`GET /v1/games/{id}/eval-graph` call for that game and cached in
the `analyses` table by
`(position_id, engine_id, depth, settings_hash)`. See
[`docs/17_lazy_eval_graph/SPEC.md`](docs/17_lazy_eval_graph/SPEC.md)
for the design rationale and the 6000-game stress-test results.

**Self-hosting model:** the desktop reads
`${CHESS_COACH_DATA_DIR}/runtime/backend.json` to discover the
backend. The desktop and the backend can be on the same machine
(simplest) or on different machines sharing `CHESS_COACH_DATA_DIR`
via an NFS mount or a copy step.

## Quick start

You need three things: a working backend, a working desktop, and a way for
them to find each other. The desktop auto-discovers the backend via
`${CHESS_COACH_DATA_DIR}/runtime/backend.json`, so the only environment
variable you have to set is `CHESS_COACH_DATA_DIR` (any writable directory).

### Backend (Python)

```bash
# In a venv:
uv venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv sync --frozen --extra dev   # reproducible from uv.lock

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

Phase-by-phase status, cross-checked against the actual code and
tests on `main` as of 2026-08-04 (commit `0cf39b6`). Phases
defined per `docs/10_roadmap/implementation-roadmap-v1.md`.

| Phase | Scope | Status | Evidence on `main` |
|-------|-------|--------|---------------------|
| 0 | Architecture + ADRs | Complete (signed off 2026-05-18) | `docs/14_adrs/`, `docs/01_architecture/system-architecture.md` |
| 1 | Skeleton (Tauri fork, FastAPI boot, Redis, Qdrant, SQLite, structlog, token-auth) | Complete (monolith-first; Redis/Qdrant not deployed as separate services) | `apps/desktop/`, `services/chess_coach/gateway/` |
| 2 | Engine + Analysis core (Stockfish pool, depth-22 eval, blunder classification, eval-graph) | Complete | `services/chess_coach/engine_orch/pool.py`, `routes/eval_graph.py`, `routes/analysis.py` |
| 3 | Memory + KB + LLM Router (three-tier memory, Qdrant collections, OpenRouter, narration) | Engine-wired narration shipped (BBF-87.2 + BBF-87.2.1, 2026-08-04). Real-LLM production wiring held back. | `routes/narration.py:177` calls `engine_pool.analyze()` and feeds a real `AnalysisResult` into `pipeline.explain()`; response now carries `depth_reached`, `best_move`, `pv_moves`, `score_display` from the engine. Grounding via v2 corpus at `tests/gold/narrative/v2/corpus.json` (BBF-87.1, BBF-89). |
| 4 | Profiling (6 psychological metrics, profile dashboard, `/profiles/explain`) | Complete | `routes/profile.py`, `routes/profile_analysis.py` |
| 5 | Repertoire + Training (tree management, gap detection, FSRS, training dashboard) | Substantially complete | `routes/repertoire.py`, `routes/repertoire_recommendations.py`, `routes/training.py`, `routes/training_planner.py` |
| 6 | PDF / Vision (book ingest via chessvision.ai) | **Partial.** Chessvision.ai integration shipped at `routes/pdf_ingest.py` and `services/chess_coach/gateway/config.py:121`; tests at `tests/unit/test_pdf_ingest_route.py`, `tests/unit/test_pdftomd_metrics.py`, `tests/integration/test_pdf_import.py`. Per `implementation-roadmap-v1.md` § Phase 6 (lines 94-107), the full Phase 6 deliverable list also includes YOLOv8 diagram detector + piece-classifier CNN, PaddleOCR integration, manual-review queue, and user-correction feedback loop; these remain deferred — local YOLOv8 + PaddleOCR kept as offline fallback only. |
| 7 | Sync + Research + Reporting polish (Lichess/Chess.com sync, research digests, PDF export) | Partial | `routes/lichess_import.py` ships sync. Reporting/research polish deferred per `implementation-roadmap-v1.md`. |
| 8 | Hardening + Packaging (MSI/NSIS installer, PyInstaller sidecar, Memurai) | Not started | Windows path is a known deferred item (BBF-37); packaging work has not begun. |
| 9 | v2 directions (cloud multi-user, voice, mobile, multiplayer) | Not started; candidates only per `implementation-roadmap-v1.md` § Phase 9 | -- |

Strategic pivot to lazy eval-graph (BBF-22) is verified at 6000-game
scale (BBF-25): 43.8 s import, ~1 s first-eval per game, instant cache
hits. See `docs/17_lazy_eval_graph/SPEC.md` for the design and
`docs/CHANGELOG.md` for the full sprint history.
