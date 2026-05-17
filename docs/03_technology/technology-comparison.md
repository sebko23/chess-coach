# Technology Comparison Report

This report compares the candidate technologies for each major layer of CHESS COACH and records the chosen stack with justifications.

## Final stack (summary)

| Layer | Choice | Alternatives considered | Why |
|---|---|---|---|
| Desktop shell | Tauri 2.x | Electron, Wails | See `05_desktop_shell/`. en-croissant compatibility. |
| GUI framework | React 19 + Mantine 8 + Vite | Svelte, Vue, MUI | Inherited from en-croissant. |
| Chess board | chessground (Lichess) | react-chessboard, custom | Inherited from en-croissant; battle-tested. |
| Chess logic (client) | chess.js + shakmaty (Rust) | — | chess.js for client move-gen; shakmaty already in en-croissant. |
| Backend language | Python 3.11 | Go, Node, Rust | Best ML/AI ecosystem; psychology/NLP/embedding tooling. |
| Backend framework | FastAPI | Flask, Litestar, Django | Async-first, OpenAPI auto, WebSockets. |
| ASGI server | Uvicorn (Gunicorn manager in prod) | Hypercorn, Daphne | Standard. |
| Inter-service messaging | HTTP/REST + WebSocket + Redis Streams | gRPC, NATS, RabbitMQ | Redis Streams gives durable agent message bus without an extra broker. |
| Task queue | Celery (Redis broker) | RQ, Dramatiq, ARQ | Celery for heavy/long jobs (PGN batch import, PDF OCR). ARQ for lightweight async tasks. |
| Relational DB | SQLite (WAL) — local | PostgreSQL (optional upgrade) | Local-first, zero-admin. Postgres path documented but not required. |
| Vector DB | Qdrant | Chroma, Weaviate, Milvus, pgvector | See `04_database/`. Best perf/footprint balance for embedded deployment. |
| Object/blob store | Local filesystem (`%APPDATA%\ChessCoach\data`) | MinIO | Filesystem is enough for v1. |
| Cache | Redis | DiskCache, in-process LRU | Redis already required for Celery/streams. |
| LLM provider | OpenRouter (primary), local Ollama (optional v2) | Direct OpenAI/Anthropic | Provider abstraction + cost routing. |
| Embeddings | OpenAI text-embedding-3-small via OpenRouter (cloud) or `bge-small-en-v1.5` (local) | Voyage, Cohere | Cost vs offline tradeoff settled at runtime. |
| Chess engines | Stockfish 18 (primary), Leela, Maia, Berserk, Komodo, Ethereal | — | All UCI; abstraction layer handles them uniformly. |
| OCR | PaddleOCR (primary), Tesseract (fallback) | EasyOCR, AWS Textract | Paddle is best F1 on chess-book printed text in our pre-tests. |
| Chess diagram detection | YOLOv8 fine-tuned on chess-diagram dataset | Heuristic OpenCV | YOLO scales; heuristic fallback for low-confidence cases. |
| PDF parsing | PyMuPDF (fitz) | pdfplumber, pdfminer.six | Fastest + best for image extraction. |
| Container runtime | Docker (compose v2) | Podman | Standard on Windows via Docker Desktop. |
| Packaging | Tauri MSI/NSIS installer + sidecar PyInstaller | — | See `05_desktop_shell/`. |
| Logging | structlog → JSON → Loki (optional) | stdlib logging | Structured logs are agent-debuggable. |
| Tracing | OpenTelemetry → optional Jaeger | — | Optional; enable only when diagnosing multi-agent flow issues. |
| Testing (Py) | pytest + pytest-asyncio + hypothesis | unittest | Standard. |
| Testing (TS) | Vitest + Playwright | Jest, Cypress | Vitest is Vite-native; Playwright for E2E. |
| Lint/format (Py) | ruff + black + mypy --strict | flake8, pylint | Speed + strictness. |
| Lint/format (TS) | Biome | ESLint+Prettier | Biome unifies and is 10x faster. |
| Git workflow | Trunk + short-lived feature branches | GitFlow | Simpler for a small team / autonomous agent. |
| CI | GitHub Actions | — | Standard for OSS. |

## Detailed layer notes

### Backend language: Python vs Go vs Rust

Python wins because every other module — psychology analysis, embeddings, OCR, OpenRouter SDK, chess-specific libs (`python-chess`), PGN parsing — has a mature Python implementation. Go and Rust would require us to reimplement or wrap. We accept Python's perf cost because chess engines (the hot path) are external native processes; the Python service is glue + orchestration.

### Why FastAPI over alternatives

- Async-first → matches our long-running engine + WebSocket streaming workloads.
- Auto-generated OpenAPI → frontend TS client generation is trivial.
- Pydantic v2 → strict typed contracts (critical for inter-agent messages).
- Excellent WebSocket support → live engine eval streams, agent status, terminal panel.

### Inter-service messaging: why Redis Streams

- We already need Redis for Celery and cache → no new infra.
- Streams give us durable, replayable, consumer-group-aware messaging.
- Sufficient for our agent count (~14 modules); we are not at NATS/Kafka scale.
- gRPC was rejected as overkill for an internal-only deployment.

### LLM provider: OpenRouter only?

No — OpenRouter is the **primary** provider but the LLM layer (`llm_router`) abstracts it. We can plug:
- OpenRouter (default)
- Direct OpenAI / Anthropic (failover)
- Local Ollama / llama.cpp (offline mode, v2)

The router decides per-task based on cost tier, latency requirement, and model capability map.

## Rejected technologies (with reason)

- **Electron** — see `05_desktop_shell/`.
- **PostgreSQL as default** — too heavy for end-user local install; offered as optional upgrade.
- **MongoDB** — schema-on-read is the wrong tradeoff for a chess analytics platform where the data model is well-known.
- **Chroma as vector DB** — see `04_database/`. Qdrant is more production-ready.
- **LangChain** — heavyweight and unstable API surface. We will use the OpenAI/Anthropic/OpenRouter SDKs directly + a thin orchestration layer.
- **Direct UCI engine integration in Tauri/Rust** — we keep all engine orchestration in Python so it can be hot-reloaded, mocked, and benchmarked without rebuilding the desktop binary.
