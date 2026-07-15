# Qdrant deployment -- BBF-52

This document covers the deployment shape for the chess-coach
KB vector store after BBF-52. The KB uses
[Qdrant](https://qdrant.tech/) as its vector store; before
BBF-52 the gateway ran Qdrant in-process via `:memory:` mode,
which meant every gateway restart lost the indexed positions.

After BBF-52 the gateway can run against either:

1. **An in-process persistent store** (the `path=` branch of
   `QdrantClient`). Useful for local dev without Docker; data is
   kept in a host directory.
2. **A Qdrant sidecar** -- a separate container reached over
   HTTP. The default for `docker compose up` and CI.

The two are not mutually exclusive; the gateway selects at
startup based on `CHESS_COACH_QDRANT_URL`:

| Env value                              | Mode                          |
|----------------------------------------|-------------------------------|
| unset (default)                        | in-memory (`:memory:`)        |
| `""` (empty string)                    | in-memory (`:memory:`)        |
| `http://localhost:6333`                | sidecar, no auth              |
| `http://qdrant:6333`                   | sidecar (compose default)     |
| `https://qdrant.example.com`           | remote Qdrant                 |

## Local dev with docker compose

The recommended setup. `docker compose up --build` brings up two
containers:

- `qdrant` -- the Qdrant sidecar, image `qdrant/qdrant:v1.12.4`.
  Storage is bind-mounted to `./data/qdrant` on the host, so the
  collection survives `docker compose down` (without `-v`).
- `backend` -- the chess-coach gateway. Depends on `qdrant`
  being healthy before starting; pointed at the sidecar via
  `CHESS_COACH_QDRANT_URL=http://qdrant:6333`.

On startup the gateway calls `index_positions(...)` eagerly
(see `services/chess_coach/gateway/app.py:181-198`), which
embeds positions from the local SQLite DB and upserts them into
the sidecar's `positions` collection.

After the first start, restart cycles are sub-second: the
gateway skips the embed step if Qdrant already has a populated
collection (see `services/chess_coach/kb/pipeline.py:73-79`).

To verify the sidecar is working:

```bash
curl -sS http://127.0.0.1:6333/collections/positions \
  -H "Content-Type: application/json" | jq .
# should show points_count > 0 after a few seconds
```

## CI

`.github/workflows/smoke.yml` has three jobs since BBF-52:

- `gateway-boot` -- clean venv + boot regression test + new
  persistent-path unit test. No Qdrant needed.
- `qdrant-smoke` -- starts a real Qdrant via `docker run`,
  starts the backend pointed at it, runs the live integration
  test against `/v1/kb/index` and `/v1/kb/similar`.
- `smoke` -- the original lazy-eval-graph smoke test. Unchanged
  from BBF-47 except for the Dockerfile HEALTHCHECK fix
  (`Bearer ***` -> `Bearer devtoken123`).

The `qdrant-smoke` job uses `--link qdrant-ci:qdrant` so the
gateway container can resolve `qdrant` to the Qdrant sidecar's
IP (docker's legacy `--link` is the simplest cross-container DNS
that works without compose v2 networking inside the GHA runner).

## Configuration

| Env var                            | Default      | Notes                                  |
|------------------------------------|--------------|----------------------------------------|
| `CHESS_COACH_QDRANT_URL`           | `:memory:`   | See table above.                       |
| `CHESS_COACH_QDRANT_API_KEY`       | `""`         | Required for remote/authed Qdrant.     |

`GatewaySettings` (in `services/chess_coach/gateway/config.py`)
exposes both as `qdrant_url` and `qdrant_api_key` fields with
the same defaults.

## Verifying the sidecar manually

After `docker compose up --build`:

```bash
# 1. Backend is healthy (BBF-38+ smoke fix applies)
curl -sS http://127.0.0.1:18080/v1/system/health \
  -H 'Authorization: Bearer devtoken123'

# 2. Trigger an index (idempotent; skips if collection is populated)
curl -sS -X POST http://127.0.0.1:18080/v1/kb/index \
  -H 'Authorization: Bearer devtoken123' \
  -H 'Content-Type: application/json' \
  -d '{"limit": 5000}'
# {"status":"ok","indexed":"5000"}

# 3. Query for similar positions
curl -sS -X POST http://127.0.0.1:18080/v1/kb/similar \
  -H 'Authorization: Bearer devtoken123' \
  -H 'Content-Type: application/json' \
  -d '{"fen":"rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1","top_k":5}'
# {"query_fen":"...","hits":[{"rank":1,"fen":"...","ply":4,"game_id":"..."}], "kb_ready":true}

# 4. Inspect the sidecar's collection directly
curl -sS http://127.0.0.1:6333/collections/positions | jq .
```

## Operational notes

- **Storage size**: 384-dim float32 vectors at ~1.5 KB each. The
  default `limit=5000` index is ~7.5 MB on disk; well under the
  Qdrant single-collection defaults.
- **Restart cost**: a Qdrant container restart takes 1-3 seconds;
  the gateway reconnects on the next request. The `positions`
  collection persists via the `./data/qdrant` bind-mount.
- **Migration to a new embedding model**: the embedder and the
  collection's vector dimension are coupled at `_ensure_collection`
  time. If the embedder swaps (e.g. BBF-52's docstring mentions
  Maia embeddings as a future option), the existing collection
  must be deleted and reindexed; the index call does this
  automatically when the dimensions don't match
  (`kb/store.py:69`).
- **Production deployment**: the compose file is dev-only. For
  Phase 8 packaging, the Qdrant image would either be embedded
  as a Tauri `externalBin` (per the phase-plan) or moved to a
  managed Qdrant Cloud instance with `CHESS_COACH_QDRANT_URL`
  pointed at the cluster.

## History

- BBF-52 (2026-07-15) -- initial sidecar deployment, CI coverage,
  Dockerfile HEALTHCHECK fix.
- BBF-41 (2026-07-14) -- added `qdrant-client` dep + `kb/embedder.py`
  and `kb/store.py` already accepted `qdrant_url` as an unused
  parameter.
- BBF-17 era (2026-07-13) -- the original `:memory:`-only
  PositionStore predates BBF-41; the `qdrant_url` parameter
  was added in anticipation of BBF-52.