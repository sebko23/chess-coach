# Multi-Agent Workflow

## Concept

CHESS COACH is built as a **society of cooperating specialized agents** rather than one monolithic LLM-driven loop. Each agent is a Python service (or service-internal worker) with a narrow, well-defined responsibility, a documented API, structured logs, and independent observability.

Agents communicate via three channels:

1. **HTTP/REST** for synchronous request/response (frontend → backend, agent → agent for short calls).
2. **WebSocket** for streaming results (engine analysis, live coaching, log tailing).
3. **Redis Streams** for asynchronous fire-and-forget / pub-sub / durable event flow (agent message bus).

## Agent roster (14 modules)

Full spec for each module is in `docs/02_modules/`. Brief role summary:

| # | Module | Lifecycle | Primary trigger |
|---|---|---|---|
| 1 | GUI Agent | resident (Tauri proc) | User input |
| 2 | Chess Analysis Agent | resident (Py worker) | Position/game submitted |
| 3 | Engine Orchestrator | resident | Analysis request |
| 4 | Psychological Profiling Agent | scheduled + on-demand | Game ingest / dashboard view |
| 5 | Knowledge Base Agent | resident | Query / new content |
| 6 | PDF/Vision Agent | on-demand (Celery) | Book upload |
| 7 | Training Planner | scheduled + on-demand | Plan view / lesson generation |
| 8 | Repertoire Agent | resident | Repertoire edit / explore |
| 9 | Research Agent | scheduled (cron) | Topic monitor |
| 10 | Memory Agent | resident | Any agent reads/writes memory |
| 11 | Reporting Agent | on-demand | Report request |
| 12 | Debug Agent | resident | Error / health probe |
| 13 | Synchronization Agent | scheduled | Lichess/Chess.com pull |
| 14 | LLM Router | resident (library, not its own service) | Any LLM call |

## Orchestration topology

```
┌─────────────────────────────────────────────────────────────────┐
│                         Tauri shell                              │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────────────┐  │
│  │  React UI    │──│  Tauri commands│──│  GUI Agent (TS)      │  │
│  └──────────────┘  └────────────────┘  └──────────────────────┘  │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP/WS (localhost:8765)
┌────────────────────────────▼─────────────────────────────────────┐
│                  Backend gateway (FastAPI)                       │
│   Routes → service agents over Redis Streams + direct calls      │
└─┬────────┬────────┬────────┬────────┬────────┬─────────────┬─────┘
  │        │        │        │        │        │             │
  ▼        ▼        ▼        ▼        ▼        ▼             ▼
 Engine  Analysis  Profile  Memory  KB     Training      Repertoire
 Orch.   Agent     Agent    Agent   Agent  Planner       Agent
  │        │        │        │        │        │             │
  └────────┴────────┴───┬────┴────────┴────────┴─────────────┘
                       │
              Redis Streams (bus) + Redis (cache/queues)
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
      SQLite        Qdrant        Filesystem
```

## Message bus design (Redis Streams)

- Stream-per-topic: `events.games.imported`, `events.engine.analysis.ready`, `events.profile.metric.updated`, `events.book.ingested`, `events.lesson.created`, …
- Each agent declares its **consumer group** and its **interested streams** in its `agent.yaml` manifest. Manifests are loaded at startup; the bus router validates.
- Messages are versioned (`schema_version` field). Breaking schema changes require a new stream name.
- Dead-letter stream `events._dlq` catches unhandled errors with full context.
- Optional snapshot to SQLite `agent_messages` table for audit/replay.

## Agent message envelope (canonical)

```json
{
  "id": "uuid7",
  "ts": "2026-05-18T01:55:00Z",
  "producer": "engine_orchestrator",
  "topic": "events.engine.analysis.ready",
  "schema_version": 1,
  "correlation_id": "uuid7-or-null",
  "causation_id": "uuid7-or-null",
  "payload": { /* topic-specific Pydantic-validated */ },
  "trace_id": "otel-trace-id"
}
```

- `correlation_id` ties together a chain of work (e.g. user clicks Analyze → many events share one correlation_id).
- `causation_id` is the parent event id (enables causal graph reconstruction).
- `trace_id` is the OpenTelemetry trace, when tracing is enabled.

## Conversation patterns

We define a small set of **named conversation patterns** so agent code stays consistent:

### P1 — Request/Reply (synchronous)
Used for: GUI → backend; agent → memory_agent (read).
Mechanism: HTTP/REST.
Timeout: 5 s default; long calls must use P2.

### P2 — Async Job (durable, long-running)
Used for: PGN batch import, PDF OCR, deep engine analysis, lesson generation.
Mechanism: Celery task → on completion, publish event on Redis Stream → GUI subscribes via WebSocket.
Client gets a job_id immediately and can poll or subscribe.

### P3 — Streaming (live updates)
Used for: engine eval streaming, live coaching transcript, log tailing.
Mechanism: WebSocket from GUI to backend gateway; backend gateway subscribes to a Redis Stream filtered by correlation_id.

### P4 — Pub/Sub (broadcast events)
Used for: "a new game was imported", "a metric was updated".
Mechanism: Redis Stream consumer groups; any interested agent reacts.

### P5 — Saga (multi-step transaction with compensations)
Used for: "Ingest a new book" — PDF parse → diagram detect → FEN reconstruct → embed → index → store. Each step publishes an event; a small **Saga Coordinator** in the Reporting Agent watches and emits failure-compensations if a step DLQs.
Mechanism: Redis Streams + a `sagas` SQLite table tracking state.

## Failure handling

- **Retries**: per-task, exponential backoff with jitter, max 3 attempts. Configured per Celery task.
- **Dead letter**: After max retries → `events._dlq` + SQLite `failed_jobs` table + visible in Debug panel.
- **Compensations**: Saga steps register their compensation function. On saga abort, compensations run in reverse order.
- **Circuit breaker**: LLM Router and external APIs (Lichess, Chess.com, OpenRouter) wrap calls in a circuit breaker (`pybreaker`). Open circuit → return stale cached result if available, else 503 to caller.
- **Healthchecks**: every agent exposes `/health` (liveness) and `/ready` (readiness). Debug Agent aggregates.

## Inter-agent dependency rules

To prevent cycles and tangled coupling:

1. **Tier 0 (infrastructure)**: SQLite, Qdrant, Redis. No deps.
2. **Tier 1 (data-only agents)**: Memory Agent, Knowledge Base Agent. Depend only on Tier 0.
3. **Tier 2 (compute agents)**: Engine Orchestrator, Chess Analysis Agent, PDF/Vision Agent, Psychological Profiling Agent, LLM Router. Depend on Tier 0 + Tier 1.
4. **Tier 3 (planning/decision agents)**: Training Planner, Repertoire Agent, Research Agent. Depend on Tier 0–2.
5. **Tier 4 (presentation/admin agents)**: GUI Agent, Reporting Agent, Debug Agent, Synchronization Agent. Depend on any lower tier.

A Tier-N agent may NOT call a Tier-N+M agent directly. Higher tiers reach lower tiers; the reverse must go via Redis Streams (events) — never direct calls. This is enforced by a small linter that scans imports + HTTP client target URLs at CI time.

## Observability

- **Logs**: structlog → JSON to stdout → docker logs → Loki (optional).
- **Metrics**: Prometheus client on each agent → `/metrics` endpoint → scraped by a single Prometheus sidecar (optional).
- **Traces**: OpenTelemetry spans propagated via `trace_id` in the message envelope.
- **Debug Panel** (GUI): live view of agent statuses, last 100 events per topic, DLQ contents, retry buttons.

## Why not a single big LLM agent loop?

A single Agent-Zero-style mega-loop driving everything via LLM tool calls would:
- Burn tokens on every chess decision (cost).
- Be non-deterministic for things that should be deterministic (engine eval, PGN parsing).
- Be hard to test (LLM in the loop).
- Be hard to scale (one model bottleneck).

Instead, LLMs are used **surgically** — for natural-language coaching output, psychological narrative generation, semantic search query rewriting, lesson narration, and Research-Agent web reasoning. Everything else is deterministic Python.
