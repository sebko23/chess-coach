# CHESS COACH GUI ↔ Backend Protocol — v1.0

**Document version**: 1.0.0
**Document license**: **CC-BY-4.0** (this specification is distinct from, and independent of, the license of any software that implements it).
**Status**: STABLE. Cleared for publication 2026-05-18 following OSS counsel review (R1 and R2 applied; counsel's verdict: "this protocol contract supports the conclusion that the GUI and Backend are separate works in an aggregate under GPL-3.0 §5").
**Implementations**: This specification is intended to be implementable by any third party in either direction. A conforming GUI may speak this protocol to a conforming Backend without any code or build-time dependency between the two.

---

## 0. Scope and Intent

This document is the **complete and public contract** between any CHESS COACH-conformant graphical user interface (the **"GUI"**) and any CHESS COACH-conformant analysis/coaching backend service (the **"Backend"**). The two components communicate exclusively via the messages, endpoints, and topics defined here.

This specification deliberately:

- contains no code or proprietary types,
- assigns no preferred implementation language or framework to either side,
- is licensed CC-BY-4.0 so a third party may publish a conforming implementation under any license they choose,
- versions independently of either implementation,
- defines conformance such that the GUI and Backend are interchangeable with alternative implementations.

The Backend MAY be operated standalone via its CLI and HTTP API without any GUI. The GUI MAY be operated against any Backend that conforms to this specification.

The specification covers Phase-1 functionality of CHESS COACH (engine analysis, grounded LLM narration, game storage, position queries, opening explorer, jobs, and health). Later versions (1.1, 1.2, …) will add endpoints for additional features (vector knowledge base, repertoire management, training plans, profile metrics, etc.). Forward-compatibility rules in §11 apply.

---

## 1. Transport, Encoding, and Addressing

### 1.1 Transports

- **REST**: HTTP/1.1 over TCP. TLS not required when both endpoints are on the local loopback interface; required otherwise. Servers MAY refuse non-loopback connections.
- **Streaming**: WebSocket (RFC 6455) over TCP, sharing the same TLS posture as REST.
- **Optional CLI**: A conforming Backend SHOULD also expose a textual CLI for offline operation; the CLI is **not** governed by this protocol document.

### 1.2 Encoding

- All payloads are **UTF-8 JSON** unless an endpoint explicitly negotiates another media type (file upload endpoints use `multipart/form-data`; downloads return their indicated `Content-Type`).
- Timestamps are **ISO-8601** with explicit timezone (`Z` for UTC, e.g. `2026-05-18T01:55:00Z`).
- Integer chess scores are centipawns; mate scores are encoded as `{"mate": N}` where N is signed moves to mate.
- FEN strings follow the X-FEN convention as standardized by the chess community; the Backend MUST accept any standard FEN and SHOULD canonicalize on storage.
- Move notation is **UCI** (`e2e4`, `g1f3`, `e7e8q`) on the wire. SAN may be returned as an additional field for human display but is never authoritative.

### 1.3 Addressing and Discovery

- The Backend listens on a TCP port discovered at startup. The Backend writes a connection descriptor to a well-known file (see §1.4) for the GUI to read.
- The Backend MUST NOT bind to a non-loopback interface unless explicitly configured to do so.
- A GUI MAY override the discovery file path via an environment variable or command-line flag and connect to a Backend at any address.

### 1.4 Connection Descriptor File

A conforming Backend, on startup, writes one file:

```
${CHESS_COACH_DATA_DIR}/runtime/backend.json
```

with mode `0600` and these contents:

```json
{
  "protocol_version": "1.0",
  "base_url": "http://127.0.0.1:8765",
  "ws_url": "ws://127.0.0.1:8765/ws",
  "session_token": "<base64url-32-bytes>",
  "pid": 12345,
  "started_at": "2026-05-18T01:55:00Z"
}
```

`CHESS_COACH_DATA_DIR` defaults to `%APPDATA%\ChessCoach\data` on Windows, `~/.local/share/chess-coach/data` on Linux/macOS. A GUI MUST be able to override this directory via the environment variable `CHESS_COACH_DATA_DIR`.

The `session_token` is the credential for **all** subsequent REST and WS calls (see §2). Tokens rotate on every Backend restart.

### 1.5 No Co-process Coupling

This specification does **not** require either side to spawn or supervise the other. A conforming Backend may be started by:

- a Tauri-based GUI via `tauri-plugin-shell` (current default for the reference implementation),
- a system service manager,
- a manual command line,
- a Docker container,
- a remote server reachable over LAN.

A conforming GUI may be started by:

- the user double-clicking a desktop shortcut,
- a third-party launcher,
- not at all (the Backend functions standalone).

Neither side is privileged in the lifecycle of the other.

---

## 2. Authentication

- Every REST request MUST carry `Authorization: Bearer <session_token>`.
- Every WS connection MUST carry the same header on the upgrade request.
- The Backend MUST reject any request whose token does not match the current `session_token`.
- Tokens are **opaque** to the GUI; the GUI MUST NOT parse them.
- Tokens rotate on Backend restart; the GUI re-reads `backend.json` and reconnects on `401 Unauthorized`.

### 2.1 Standard Bearer Credential (R1)

The `session_token` is a **standard bearer credential**, not a privileged handshake between specific binaries. Specifically:

- Any client that can read the connection descriptor file (§1.4) — or that has been provided the token out-of-band by the operator — MAY authenticate. The Backend MUST NOT restrict authentication by **process identity, binary signature, launch parent, working directory, executable path, code-signing certificate, or any other property tied to who started the client**. Authentication is solely a check of bearer-token equality.
- A Backend operator MAY configure a **static token** via the `CHESS_COACH_BACKEND_TOKEN` environment variable (or equivalent configuration file entry) for remote, LAN, or multi-client deployments. When a static token is configured, the Backend MAY skip writing the `session_token` field to `backend.json`, or MAY write a static value there; either is conforming.
- The `CHESS_COACH_DATA_DIR` environment variable (§1.4) lets any client point at the descriptor file at any path. There is no protocol-defined restriction on which clients may read the descriptor.
- The token is a **session credential**, not a cryptographic key in the sense of GPL-3.0 §6 "Installation Information": it does not verify the client binary's provenance, is not bound to any binary's identity, is freshly generated at each Backend restart, and may be re-read by any user-built modified GUI on the same machine.

In short: the auth mechanism is the standard "bearer token from a known location, or supplied by the operator" pattern. Third-party GUIs and third-party Backends interoperate via the same auth surface that the reference implementation uses; there is no privileged channel.

---

## 3. Envelope Conventions

### 3.1 REST Response Envelope

All successful REST responses use one of:

- **Resource form** — the response body is the resource directly: `{ "id": …, …fields… }`.
- **Collection form** — `{"items": [...], "cursor": null|string}` for paginated lists. `cursor` is opaque; the client passes it back via `?cursor=…` to retrieve the next page.
- **Job form** — for any operation that takes longer than ~50 ms p50, the immediate response is `{"job_id": "<uuid7>", "status": "queued"}` and the actual result is delivered via `GET /jobs/{job_id}` or via subscription to `jobs.<job_id>` over WS (§5).

### 3.2 Error Envelope

All error responses use:

```json
{
  "error": {
    "code": "engine_busy",
    "message": "All engine slots are in use",
    "details": {"available_slots": 0, "queued_jobs": 4},
    "trace_id": "<otel-trace-id-or-null>"
  }
}
```

- `code` is a stable identifier from the table in §10.
- `message` is human-readable but **not** stable; the GUI MUST switch on `code` rather than parse `message`.
- `details` is endpoint-specific.

### 3.3 WebSocket Message Envelope

Every WS frame sent in either direction is a JSON object:

```json
{
  "id": "<uuid7>",
  "ts": "2026-05-18T01:55:00Z",
  "type": "event" | "subscribe" | "unsubscribe" | "ack" | "error",
  "topic": "<topic-name>",
  "correlation_id": "<uuid7-or-null>",
  "payload": { ... topic-specific ... },
  "schema_version": 1
}
```

- `subscribe` / `unsubscribe` are sent by the GUI.
- `event` and `error` are sent by the Backend.
- `ack` may be sent in either direction to confirm receipt.
- `correlation_id` ties a stream to the REST request that initiated it (e.g. an engine analysis stream's `correlation_id` equals the `job_id` of the analyze call).

---

## 4. REST Endpoints (v1.0)

All endpoints below are rooted at the `base_url` from `backend.json`.

### 4.1 Discovery and Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/protocol` | Returns `{"versions": ["1.0"], "current": "1.0"}`. Does NOT require auth. |
| `GET` | `/health` | Liveness. Returns `{"status": "ok"}` if the process is up. |
| `GET` | `/ready` | Readiness. Returns `{"status":"ready"|"degraded"|"not_ready", "components":{…}}`. |
| `GET` | `/version` | Returns `{"backend_version":"<semver>","protocol_version":"1.0","build":"<hash>"}`. |

### 4.2 Jobs

| Method | Path | Description |
|---|---|---|
| `GET` | `/jobs/{job_id}` | Returns job status and (if completed) result. |
| `POST` | `/jobs/{job_id}/cancel` | Best-effort cancellation. |
| `GET` | `/jobs?status=…&kind=…&limit=…` | Lists jobs (most-recent first). |

Job shape:

```json
{
  "job_id": "<uuid7>",
  "kind": "engine.analyze_game" | "narration.generate" | "book.ingest" | …,
  "status": "queued" | "running" | "completed" | "failed" | "cancelled",
  "created_at": "…",
  "started_at": "…|null",
  "completed_at": "…|null",
  "progress": 0.0,
  "result": { ... | null },
  "error": { ... | null }
}
```

### 4.3 Games

| Method | Path | Description |
|---|---|---|
| `POST` | `/games` | Create a game from PGN. Body: `{"pgn": "..."}`. Returns the created game. |
| `GET` | `/games?cursor=…&limit=…` | List games. |
| `GET` | `/games/{game_id}` | Game with parsed moves and headers. |
| `DELETE` | `/games/{game_id}` | Delete (requires confirmation token in body). |

Game shape (abridged):

```json
{
  "id": "<uuid7>",
  "pgn": "[Event ...] 1. e4 e5 ...",
  "headers": {"Event":"…","White":"…","Black":"…","Result":"…","Date":"…"},
  "moves": [{"ply":1,"uci":"e2e4","san":"e4","fen_after":"…","time_spent_ms":null}],
  "created_at":"…",
  "analysis_status":"not_started"|"running"|"completed"|"failed"
}
```

### 4.4 Positions

| Method | Path | Description |
|---|---|---|
| `GET` | `/positions/{fen}` | Canonicalized FEN view: legal moves, side-to-move, castling rights, ECO if known. FEN is URL-encoded. |
| `GET` | `/positions/{fen}/opening` | Opening node (name, ECO, transposition flag). |
| `GET` | `/positions/{fen}/games?cursor=…` | Games containing this position. |

### 4.5 Engines

| Method | Path | Description |
|---|---|---|
| `GET` | `/engines` | List installed engines and their capabilities. |
| `GET` | `/engines/{engine_id}` | Engine details (version, options, current state, memory mode). |
| `POST` | `/engines/{engine_id}/analyze` | Start an analysis job. Body in §6. Returns job form. |
| `POST` | `/engines/{engine_id}/configure` | Set engine UCI options within allowed bounds. |

### 4.6 Analysis

| Method | Path | Description |
|---|---|---|
| `POST` | `/analysis/games/{game_id}` | Start full-game analysis (job). |
| `GET` | `/analysis/games/{game_id}` | Latest analysis snapshot. |
| `POST` | `/analysis/positions` | Body: `{"fen":"…","engine_id":"…","depth":22,"multipv":3}`. Short-form sync if estimated time < 1 s; otherwise job form. |

Analysis snapshot shape (abridged):

```json
{
  "game_id": "…",
  "engine_id": "sf18",
  "engine_version": "18.0",
  "settings_hash": "…",
  "created_at": "…",
  "per_move": [
    {
      "ply": 24,
      "played_uci": "f3e5",
      "best_uci": "d4d5",
      "eval_cp_before": +35,
      "eval_cp_after": -120,
      "classification": "blunder",
      "motifs": ["missed_fork"],
      "top_pvs": [
        {"line":["d4d5","e7e6","…"],"eval_cp":+35,"depth":22},
        …
      ]
    }
  ]
}
```

### 4.7 Narration

| Method | Path | Description |
|---|---|---|
| `POST` | `/narration/move` | Body: `{"game_id":"…","ply":N}`. Returns job form. |
| `POST` | `/narration/game-summary` | Body: `{"game_id":"…"}`. Returns job form. |

Narration result shape:

```json
{
  "narration_id": "<uuid7>",
  "text": "After 24. Nxe5?, Black wins material because the knight was defended only by the queen, which White's king pin made unable to recapture safely.",
  "grounding": {
    "engine_id":"sf18",
    "engine_version":"18.0",
    "ground_truth_hash":"…",
    "validator_result":"consistent" | "fallback_template_used",
    "claims_checked": ["best_move","eval_direction","named_motif"]
  },
  "llm": {
    "task_profile":"narration",
    "provider_route":"openrouter",
    "tokens_in": 1234,
    "tokens_out": 245,
    "cached": false
  }
}
```

A Backend MUST refuse to emit narration that is not consistent with engine ground truth (see §8). When the LLM fails to produce a consistent narration, the Backend substitutes a deterministic template-rendered narration and sets `validator_result: "fallback_template_used"`.

### 4.8 Knowledge Base (FTS subset, v1.0)

| Method | Path | Description |
|---|---|---|
| `GET` | `/kb/search?q=…&filters=…&cursor=…` | Hybrid (BM25 / FTS5) search over indexed text content. Vector search is reserved for v1.1+. |
| `GET` | `/kb/openings/{eco}` | Opening node. |

v1.1 will add vector-search endpoints; the v1.0 response shape is forward-compatible (extra fields permitted).

### 4.9 Memory (minimal v1.0)

| Method | Path | Description |
|---|---|---|
| `GET` | `/memory/recall?query=…&tier=episodic` | Episodic-tier recall only in v1.0. Semantic and procedural tiers reserved for v1.1+. |
| `POST` | `/memory/remember` | Body: `{"text":"…","tags":[…]}`. |

### 4.10 Debug (out-of-band)

| Method | Path | Description |
|---|---|---|
| `GET` | `/debug/status` | Aggregate system status for the in-GUI Debug Panel. |
| `GET` | `/debug/jobs/dlq` | Dead-lettered jobs. |
| `POST` | `/debug/jobs/{job_id}/retry` | Re-enqueue. |

---

## 5. WebSocket Topics (v1.0)

The GUI subscribes by sending `{"type":"subscribe","topic":"<name>","correlation_id":"…"}`.

| Topic | Direction | Payload |
|---|---|---|
| `jobs.<job_id>` | Backend → GUI | `{"status":…,"progress":…,"result?":…,"error?":…}` events for a specific job |
| `engine.<job_id>` | Backend → GUI | Streaming `info` lines from an engine analysis job, parsed into structured form |
| `narration.<job_id>` | Backend → GUI | Streaming tokens of narration generation (if the LLM provider supports token streaming) |
| `system.health` | Backend → GUI | Periodic (10 s) health snapshot |
| `system.log.<level>` | Backend → GUI | Live log tail; subscribed by the Debug Panel only |

The Backend MAY drop messages on the floor for a client whose receive queue exceeds an internal threshold; clients SHOULD detect this via `system.health` `ws_dropped` counter and request a snapshot via the equivalent REST endpoint.

### 5.1 Diagnostic-only topics (R2)

The `system.log.<level>` topic is **advisory / diagnostic only**. A conforming GUI MUST NOT condition any user-visible behavior or any business-logic decision on the content, structure, or presence of log messages. Specifically: log lines are intended for the in-GUI Debug Panel and for developer observability; they are not part of the protocol's control plane. Log message text, fields, and levels MAY change in any minor protocol version without breaking conformance.

---

## 6. Engine Analysis Request — Canonical Form

```json
POST /engines/{engine_id}/analyze
{
  "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
  "depth": 22,
  "multipv": 3,
  "options": {
    "Threads": 4,
    "Hash": 1024,
    "UCI_Chess960": false
  },
  "stream": true
}
```

- Either `depth` or `nodes` MAY be specified; if neither, the Backend chooses based on engine and memory mode. Time-limited search (e.g. `movetime`) is **not** supported because its results are not cacheable (see §7).
- `stream: true` ⇒ the Backend opens a `engine.<job_id>` topic upon job acceptance; `false` ⇒ wait for the final result.
- `options` are passed via UCI `setoption` within ranges declared by `GET /engines/{engine_id}` `capabilities.options`.

Result (engine.<job_id> final event, also stored in `engine_analyses`):

```json
{
  "engine_id":"sf18",
  "engine_version":"18.0",
  "fen":"…",
  "depth_reached": 22,
  "multipv": 3,
  "settings_hash":"…",
  "cpu_arch":"x86_64-avx2",
  "thread_count": 4,
  "pvs": [
    {"rank":1,"line":["e7e5","g1f3","…"],"eval_cp":+18,"depth_seldepth":[22,34]},
    …
  ],
  "time_ms": 2840,
  "nodes": 12_400_000
}
```

Cache key on the Backend side is the tuple `(fen, engine_id, engine_version, depth, multipv, settings_hash, cpu_arch, thread_count)`; this is **internal** and is documented here only because the cache-key fields appear in the result so that clients can correlate.

---

## 7. Determinism and Caching

- Depth-limited engine analyses are deterministic only when `thread_count == 1`. For `thread_count > 1`, the Backend MAY return results from cache or from a fresh run; the result is **functionally equivalent** but not byte-identical.
- Time-limited analyses are **not cached** and **not specified** by this protocol version.
- Cache invalidation is the Backend's responsibility; the GUI is not required to know whether a result came from cache. A `cached: true` field MAY be returned but does not affect protocol semantics.

---

## 8. Grounded Narration — Mandatory Validation

A conforming Backend MUST NOT emit a `/narration/*` response in which the prose contradicts the engine ground truth that the narration was supposedly generated from. The Backend MUST:

1. Construct an immutable **grounding payload** containing `best_uci`, `eval_cp`, `top_pvs`, `classification`, `motifs[]`.
2. Pass the grounding payload into the LLM prompt inside a delimited `<ground_truth>` block.
3. Parse the LLM's prose output to extract any concrete falsifiable claims (named best move, eval direction, named motif).
4. Cross-check each claim against the grounding payload.
5. If any claim is inconsistent — or if the LLM emits the special token `__NEED_FALLBACK__` — substitute a deterministic template-rendered narration generated purely from the grounding payload, and set `grounding.validator_result = "fallback_template_used"`.

This is normative behavior of the protocol, not an implementation detail: any conforming Backend implements it, regardless of which LLM provider it uses.

---

## 9. Versioning Policy

- This document carries a SemVer-style version (`1.0.0`, `1.1.0`, etc.).
- **Patch** versions (`1.0.1`, `1.0.2`) are editorial: clarifications, typo fixes, no normative change.
- **Minor** versions (`1.1`, `1.2`) add new endpoints, new topics, or new optional fields. Existing clients and servers continue to interoperate.
- **Major** versions (`2.0`) are breaking. The Backend MAY support multiple major versions simultaneously by exposing different `base_url` paths (e.g. `/v1`, `/v2`). The GUI selects via `GET /protocol`.
- New fields in existing response bodies MUST NOT break clients; clients MUST ignore unknown fields.
- New `error.code` values MAY be added in minor versions; clients MUST treat unknown codes as generic errors.

---

## 10. Error Code Table (v1.0)

| Code | Meaning |
|---|---|
| `auth_required` | Missing or invalid `Authorization` header. |
| `auth_token_rotated` | Token rotated; re-read `backend.json` and reconnect. |
| `not_found` | Resource does not exist. |
| `invalid_argument` | Validation error on request body or query. |
| `engine_not_installed` | Requested `engine_id` is not installed. |
| `engine_busy` | All engine slots occupied; job is queued. |
| `engine_budget_exceeded` | Memory mode (Lite/Standard/Full) would be exceeded. |
| `job_not_found` | `job_id` unknown. |
| `job_cancelled` | Job was cancelled before completion. |
| `narration_grounding_failed` | Internal: validator forced a fallback. (Reported in the result, not as a 4xx error.) |
| `llm_budget_exhausted` | Daily LLM token budget for this task profile is spent. |
| `llm_provider_unavailable` | Circuit breaker is open. |
| `rate_limited` | Per-domain rate limit (cloud APIs). |
| `unsupported_protocol_version` | Client requested a major version the Backend does not implement. |
| `internal_error` | Catch-all; includes `trace_id`. |

---

## 11. Forward-Compatibility Rules

1. **Unknown fields are ignored** on both sides.
2. **Unknown WS topics** sent by the Backend are silently dropped by the GUI.
3. **Unknown WS message types** sent by the GUI are responded to with an `error` frame (`code: invalid_argument`).
4. **Unknown REST endpoints** return `404 not_found`.
5. **Reserved namespaces**: `/v2/…` (future major), `/_internal/…` (Backend's own use, never part of the protocol), `/admin/…` (reserved for v2+).
6. Any field with a name starting `x_` is implementation-specific and not part of the protocol.

---

## 12. Conformance

A software is **Backend-conformant for protocol v1.0** if it:

- Implements all endpoints in §4 with the documented shapes.
- Implements all topics in §5.
- Honors authentication per §2.
- Honors grounded narration per §8.
- Honors versioning per §9.
- Passes the reference test vectors (§14).

A software is **GUI-conformant for protocol v1.0** if it:

- Speaks only the endpoints and topics defined here.
- Honors authentication per §2 (including re-discovery on `auth_token_rotated`).
- Honors forward-compatibility rules per §11.
- Does not assume any out-of-protocol behavior of the Backend.

Third parties are explicitly invited to publish conforming implementations of either side. The reference implementation (in the `chess_coach` repository) is one example of conformance, not a definition of it.

---

## 13. Out-of-Scope (Explicitly NOT Part of This Protocol)

- How the Backend stores data on disk.
- Which LLM provider the Backend uses.
- Which chess engines the Backend can drive (other than that they expose UCI).
- The visual rendering of any data by the GUI.
- Telemetry collection by either side (Backend implementations MUST disclose telemetry per the operator's privacy policy; the protocol itself is silent).
- Any inter-process control beyond what is exposed in §4 / §5.

In particular, the protocol does **not** require or rely on either component launching, supervising, signaling, or otherwise managing the lifecycle of the other.

---

## 14. Reference Test Vectors (sketch — full vectors at v1.0 final)

A reference test suite distributed with this specification (under MIT for the test code; CC-BY-4.0 for fixtures) will include:

- 50 sample HTTP request / response pairs covering every endpoint.
- 10 sample WS sessions including subscribe / event / unsubscribe.
- 5 narration jobs covering consistent narration, fallback-template narration, and edge cases (missing engine ground truth, token streaming).
- A linter that consumes the JSON schemas (§15) and validates any captured trace.

---

## 15. Schema Index

Machine-readable JSON Schema documents for every payload in §4–§6 are published alongside this specification:

```
/specs/v1.0/schemas/
  job.schema.json
  game.schema.json
  position.schema.json
  engine.schema.json
  analyze-request.schema.json
  analyze-result.schema.json
  narration-result.schema.json
  error.schema.json
  ws-envelope.schema.json
```

The schemas are normative; the prose in this document is explanatory.

---

## 16. Changelog

- **1.0.0** (2026-05-18): First stable publication. Applied counsel revisions R1 (explicit standard-bearer-credential language in §2.1) and R2 (explicit advisory-only language for `system.log.*` topics in §5.1). Counsel verdict: separate-works position supported.
- **1.0.0-draft.1** (2026-05-18): Initial draft for legal review.

---

## Appendix A — Rationale for OSS Counsel

*This appendix is non-normative. It is included only to support the legal analysis being conducted on this specification under GPL-3.0 §5 "aggregate" / §6 conveyance considerations. It will be retained in the final published version because future readers benefit from understanding the design intent.*

The protocol is structured to make the following facts **observable and third-party-verifiable**:

1. The Backend's operation does not depend on which GUI is connected (§1.5).
2. The GUI's operation does not depend on which Backend implementation is connected, beyond conformance to this document (§12).
3. The two components communicate **only** via this protocol; there is no shared memory, no FFI, no dynamic linking, no shared object code.
4. The protocol carries no proprietary types, no implementation-specific encodings, and no co-process control surfaces (§13).
5. The specification is published under CC-BY-4.0, **independent** of the license of any implementation; a third party may publish a conforming implementation of either side under any license.
6. The reference implementation is offered as **one example** of conformance, not as a definition of it (§12).
7. The Backend is fully usable standalone via its CLI and HTTP API (§1.5), independent of any GUI.

These design choices were made for two reasons: (a) good software engineering (genuine modularity, independent evolvability), and (b) to give the project the strongest possible position that the GUI and Backend are **separate works in an aggregate**, not a single combined work, under GPL-3.0 §5 final paragraph.

We specifically ask OSS counsel to review §1–§8 for any clauses that would weaken this position — for example, any required co-process behavior, any privileged channel, any implementation coupling, or any §6 ("Installation Information") obligations the protocol triggers — and to recommend revisions before v1.0.0 is cut.
