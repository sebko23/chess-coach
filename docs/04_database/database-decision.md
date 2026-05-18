# Database Architecture Decision

## Decision summary

- **Relational / structured data**: **SQLite** (WAL mode) — local-first, zero-admin. Optional **PostgreSQL** upgrade path documented.
- **Vector data**: **Qdrant** (embedded mode for single-user, server mode if multi-user later).
- **Cache / queues**: **Redis** (already required for Celery and Redis Streams).
- **Blob storage**: **Local filesystem** under a known data dir (`%APPDATA%\ChessCoach\data` on Windows).

## Why SQLite over PostgreSQL for v1

| Aspect | SQLite (WAL) | PostgreSQL |
|---|---|---|
| End-user install complexity | ✅ Zero (file-based) | ❌ Service install, port mgmt |
| Concurrent readers | ✅ Many | ✅ Many |
| Concurrent writers | ⚠️ Serialized (one at a time) | ✅ True parallel |
| Max practical DB size | ~1 TB (we'll never approach) | unbounded |
| Backup | ✅ copy a file | ⚠️ pg_dump |
| Cross-machine sync | ⚠️ manual (file copy / git-annex) | ✅ replication |
| Portability of user data | ✅ trivial | ❌ |
| Maintenance | ✅ none | ⚠️ vacuum, indexes, version mgmt |
| Dev velocity | ✅ no infra | ⚠️ docker-compose at minimum |

For a single-user desktop app, the only SQLite weakness that matters is concurrent writers. We mitigate by:
- Single writer thread per logical store, managed by a small `db_writer` actor (Python). All write requests are funneled through it.
- Read pool sized to N where N = max(CPU, 4).
- Heavy bulk imports (PGN, PDF batches) take an explicit `BEGIN IMMEDIATE` and run in their own short connection.

**Postgres upgrade path**: SQLAlchemy 2.x with the SQLite + Postgres dialects both supported. Migrations via Alembic. A user who outgrows SQLite (e.g. running CHESS COACH as a multi-user club server) sets `DATABASE_URL=postgresql://…` and the same schema applies. We will NOT use SQLite-only features (e.g. `JSON1`-specific syntax) where Postgres alternatives exist.

## Why Qdrant over alternatives for vectors

| Vector DB | Embedded mode | Footprint | Filter perf | License | Verdict |
|---|---|---|---|---|---|
| **Qdrant** | ✅ (Rust binary, single file) | ~40 MB | ✅ excellent (HNSW + payload filters) | Apache-2.0 | **Chosen** |
| Chroma | ✅ (Python) | small | ⚠️ degrades at scale | Apache-2.0 | Rejected — production issues reported in 0.4.x, frequent breaking changes |
| Weaviate | ❌ requires server | large | ✅ | BSD-3 | Overkill for local |
| Milvus | ❌ requires server cluster | very large | ✅ | Apache-2.0 | Overkill |
| pgvector | only if Postgres present | depends | ✅ | PostgreSQL | Rejected — couples to Postgres which we don't want as a hard dep |
| FAISS (raw) | ✅ | minimal | ❌ no filters, no persistence layer | MIT | Rejected — we'd reimplement Qdrant |

Qdrant runs **embedded** (in-process or sidecar binary) for desktop deployment. Same Qdrant binary can be promoted to a server later without data migration (snapshot import).

### What goes in Qdrant

| Collection | Vector dim | Source | Use |
|---|---|---|---|
| `book_chunks` | 768 (bge-small) or 1536 (oai-3-small) | PDF book chunks | Semantic search across user's library |
| `pgn_annotations` | same | NAG/commentary from PGNs | "Find positions where commenter says X" |
| `position_concepts` | same | Engine + heuristic labels per position | Concept-based position retrieval |
| `user_lessons` | same | Past coaching sessions | Memory recall |
| `engine_analyses` | optional, smaller dim | Compressed analysis embeddings | Cluster similar analyses |

Embedding dim is chosen at install time (offline `bge-small` 384/768 vs cloud `text-embedding-3-small` 1536). Each collection is created with the active dim; migration utility re-embeds if user switches provider.

## SQLite schema (high-level — full ERD in `01_architecture/`)

Core tables:

- `games` — one row per imported game (PGN-derived).
- `positions` — deduplicated FEN strings (canonicalized) with stats.
- `moves` — per-game moves, joins games × positions.
- `engine_analyses` — depth, score, PV, engine_id per (position_id, engine_id, depth).
- `engines` — installed engines + metadata.
- `books` — PDF books in user library.
- `book_pages` — per-page text + extracted diagrams.
- `diagrams` — detected board images + reconstructed FEN + confidence.
- `lessons` — generated/curated coaching units.
- `lesson_attempts` — user attempts at lesson positions.
- `profile_metrics` — psychological/behavioral metrics over time (player_id, metric_name, value, computed_at).
- `players` — known players (user + opponents).
- `repertoire_lines` — opening repertoire entries.
- `cloud_sync_state` — last-sync cursor for Lichess/Chess.com.
- `agent_messages` (optional persistence of Redis Stream snapshots for audit).

All IDs are UUIDv7 (sortable, opaque, no leakage of count).

## Caching strategy

- **L1 in-process LRU** (`functools.lru_cache` or `cachetools.TTLCache`) for hot per-request lookups.
- **L2 Redis** for cross-process / cross-agent caches: engine analyses, embeddings, LLM responses (keyed by prompt+model hash), Lichess/Chess.com API responses.
- **L3 SQLite materialized tables** for expensive aggregates (heatmaps, profile metrics).
- Cache invalidation: TTL + version-tag for engine analyses (so engine version bumps invalidate cleanly).

## Long-term memory design

Three tiers:

1. **Episodic memory** — `lessons`, `lesson_attempts`, `agent_messages` audit. SQL.
2. **Semantic memory** — vector collections in Qdrant.
3. **Procedural memory** — skills/playbooks stored as markdown files in `data/skills/`, indexed into Qdrant. Mirrors Agent Zero's own skill system.

Memory access goes through the **Memory Agent** (see `02_modules/`) which arbitrates between the three tiers.

## Portability + Windows compatibility

- SQLite + Qdrant + Redis all run native on Windows (Redis via Memurai or WSL2 — we will ship a Memurai sidecar for end users to avoid WSL dependency).
- Single data dir `%APPDATA%\ChessCoach\data` is fully self-contained → user can move/back-up by copying the folder.
- A `chess-coach data export` CLI command will produce a versioned tarball for support / migration.

---

## Post-Review Addenda (2026-05-18)

### A-F8. Embedding model + chunking strategy

**Embedding model (default, pending user confirmation per U3)**: `nomic-embed-text` via Ollama (768-dim, offline-capable, Apache-2.0). Cloud fallback: `text-embedding-3-small` (1536-dim) via OpenRouter. The Qdrant collection dim is set at install time; switching providers requires a re-embed (utility provided).

**Chunking strategy for chess books (mandatory)**: chunking MUST be diagram-boundary-aware. Specifically:
- Do not split a chunk across a diagram annotation. A chunk ends just before the next `[diagram N]` marker (extracted by the PDF/Vision pipeline) and starts just after the diagram's caption.
- Chunks include surrounding context: 1 paragraph before + the diagram caption + 1 paragraph after, then continue normally until the next diagram or section boundary.
- Each chunk carries metadata: `book_id`, `page`, `before_diagram_id` / `after_diagram_id`, `section_title`, `move_sequence` (if any was OCR'd nearby).
- This is the explicit response to the external review (§5.2): naive 512-token splitting destroys retrieval quality for chess books.

**Vector retrieval interface (mandatory)**: the application code talks to a `VectorStore` abstraction in `libs/chess_coach_db/`, not directly to Qdrant. The Qdrant adapter and a hypothetical `pgvector` adapter implement the same interface. Migrating to pgvector if/when we move to Postgres (multi-user mode) becomes a backend swap, not an API rewrite.

### A-F9. Engine analysis cache: size cap + LRU eviction

The `engine_analyses` SQLite table can grow without bound for a serious player. Mitigation (post-review):

- Configurable size cap (default: 2 GB of cache rows, or ~5 million entries — whichever first).
- LRU eviction performed at the `(fen, engine_id)` prefix: when evicting we drop all depth/multipv variants for the least-recently-used `(fen, engine_id)` together, not piecemeal. This preserves the cache's value model: an entry is either fully present (all depths) or fully absent.
- A nightly maintenance job (Celery beat or a simple cron in the desktop shell) runs the eviction.
- The user can manually trigger eviction or set a smaller cap from the Settings panel.
