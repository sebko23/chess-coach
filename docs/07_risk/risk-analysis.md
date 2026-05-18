# Risk Analysis

Risks are scored by **likelihood** (L: 1–5) × **impact** (I: 1–5) → priority. Top-priority risks have mitigations defined and owners (module name).

## Top risks

| # | Risk | L | I | LxI | Mitigation | Owner |
|---|---|---|---|---|---|---|
| R1 | en-croissant upstream breakage on fast cadence (~800 PRs) | 5 | 4 | 20 | Fork from a pinned tag; CHESS COACH code lives only in `panels/coach/` and parallel modules; periodic rebase ritual documented; no edits to upstream files outside a small allow-list | GUI Agent |
| R2 | GPL-3.0 contamination of backend AI services | 3 | 5 | 15 | Backend AI services run as **separate processes** communicating only over documented HTTP/WS protocol; no linking to en-croissant code; license boundary documented in `LICENSING.md` | Lead arch. |
| R3 | FEN reconstruction accuracy from PDFs below useful threshold | 4 | 4 | 16 | Multi-stage pipeline (detector → orientation → piece classifier → legal-position validator); confidence threshold routes low-confidence diagrams to manual-review queue; user corrections feed a fine-tuning dataset | PDF/Vision |
| R4 | LLM cost runaway from autonomous agents | 4 | 4 | 16 | LLM Router enforces per-task daily budgets; circuit breaker; cache by prompt hash; default to cheap models for non-narrative tasks; Research Agent budget is hard-capped | LLM Router |
| R5 | Engine version mismatch invalidates cached analyses silently | 3 | 4 | 12 | Cache keys include `(engine_id, engine_version, settings_hash)`; engine upgrade triggers cache invalidation; a `reanalysis_queue` rebuilds on demand | Engine Orch. |
| R6 | Prompt injection from user PDFs / cloud games | 3 | 4 | 12 | Untrusted content wrapped in delimited blocks; system prompts forbid acting on instructions inside user content; no LLM-driven action execution in main loop | LLM Router |
| R7 | SQLite write contention under heavy ingest | 3 | 3 | 9 | Single-writer actor; WAL mode; batch writes; long-running imports use BEGIN IMMEDIATE on their own connection | Memory |
| R8 | Docker dependency excludes users who don't want Docker Desktop | 4 | 3 | 12 | Ship a PyInstaller sidecar of the full backend for end-user releases; Docker is dev-only by default | DevOps |
| R9 | Psychological metrics over-claim precision → misleading users | 3 | 4 | 12 | Every metric ships with confidence intervals, sample size, and "explain" view; UI labels metrics as "experimental" until N games threshold | Profiling |
| R10 | Lichess / Chess.com API rate-limit / TOS issues | 3 | 3 | 9 | Strict rate limits with backoff; ETag use; user provides own API tokens; document TOS posture | Sync |
| R11 | OCR failure on non-Latin / non-English chess books | 4 | 3 | 12 | PaddleOCR supports many scripts; per-book language hint; fallback to Tesseract; figurine-notation detector independent of language | PDF/Vision |
| R12 | Diagram piece-classifier mis-trained on stylistic outliers | 3 | 3 | 9 | Train on a diverse dataset (ChessBase, Dover, modern publishers); user-correction feedback loop; ensemble with a heuristic SVM as sanity check | PDF/Vision |
| R13 | Qdrant data corruption (single-user, no replication) | 2 | 4 | 8 | Daily snapshot to disk; user data export bundle includes Qdrant snapshot; collection rebuild from SQL+files is possible if catastrophic | KB |
| R14 | Tauri auto-updater compromise (key theft) | 1 | 5 | 5 | Signing key offline; release process from a single secured machine; HSM eventually | DevOps |
| R15 | Memory leak in long-running agents | 3 | 3 | 9 | Celery `--max-memory-per-child`; service restart policy on memory cap; periodic load-test in CI | Debug |
| R16 | Token leakage in logs / support bundles | 2 | 5 | 10 | Logger redaction filter; support-bundle sanitizer scrubs known patterns; tests for redaction | Security |
| R17 | Architectural drift (agents start violating tier rules) | 4 | 3 | 12 | Tier-rule linter in CI; documented in `06_multi_agent/`; reviewed at every refactor | Lead arch. |
| R18 | LLM provider outage → coaching unavailable | 3 | 3 | 9 | Multi-provider router; fallback chain; offline local-model option (v2) | LLM Router |
| R19 | User data loss from a bad migration | 2 | 5 | 10 | Alembic migrations with down-migrations; auto-snapshot of `%APPDATA%\ChessCoach\data` before any migration; rollback documented | Memory |
| R20 | Autonomous-agent foot-gun (Research Agent ingests something inappropriate) | 3 | 3 | 9 | Source allowlist; LLM relevance judge before ingest; user can review/discard digest before it lands in KB | Research |

## Cross-cutting risks

- **Scope creep**: 14 modules + 12 deliverables + an evolving chess research agenda → strong roadmap gating (see `10_roadmap/`). Phase gates: nothing proceeds past gate without the prior phase's exit criteria.
- **Single-developer continuity** (Agent Zero + user): if Agent Zero context is lost, the architecture package itself must be self-sufficient documentation for a new agent (or human) to pick up. Hence the extensive docs/.
- **Hallucinated tooling**: agent might invent libraries that don't exist. Mitigation: every dependency pinned and `pip-audit`/`pnpm audit` runs in CI; first install of any new lib is verified.

## Decision points that must NOT be made autonomously

Agent Zero will not, without explicit user approval, do any of:
- change the desktop shell choice
- adopt a paid SaaS dependency that bills the user
- change the license of the project or any sub-component
- delete user data (only the user, via confirmation UI, can do this)
- publish/upload anything outside the local machine
- alter `.a0proj/` or repo identity files

---

## Post-Review Risk Additions (2026-05-18)

Risks newly identified or re-prioritized by the Claude.ai external review (see `docs/13_review_response/`).

| # | Risk | L | I | LxI | Mitigation | Owner |
|---|---|---|---|---|---|---|
| R21 | Memurai redistribution license / maintenance trajectory | 3 | 4 | 12 | Phase-1 monolith-first removes Redis as hard dep; evaluate Valkey when Redis reintroduced | DevOps |
| R22 | LLM narration hallucinates content contradicting engine ground truth | 4 | 4 | 16 | Mandatory grounded-narration pipeline (Module 14 § A-F6); validator + fallback template; no free-form LLM coaching output ships without it | LLM Router |
| R23 | Engine cache invalidated by CPU arch / thread count differences across machines | 3 | 2 | 6 | Cache key includes `cpu_arch` + `thread_count` (Module 3 cache-key update); only depth-limited search cached | Engine Orch. |
| R24 | PDF parser CVE compromises main backend process | 2 | 4 | 8 | PDF parsing in isolated subprocess (no net, ro fs, mem cap, timeout) — Module 6 § A-F7 | PDF/Vision |
| R25 | 14-process deployment topology stalls Phase 1 delivery | (eliminated) | — | — | Monolith-first deployment + module-level decomposition; agents extract to processes only when empirically required | Lead arch. |
| R26 | Saga framework built before any saga flows exist | (eliminated) | — | — | No saga code until a real saga flow demands it; PDF ingest pipeline becomes linear Celery chain in Phase 6 | Lead arch. |
| R27 | GPL boundary invalidated → forced relicense after months of code | 4 | 5 | **20** | **Implementation blocked on user decision U1** (see `docs/13_review_response/response-to-review.md` § E) | Lead arch. |
| R28 | Psychological profiling metrics surface confident-but-invalid claims | 4 | 4 | 16 | Hypothesis + effect-size rigor (Cohen's d > 0.5 to surface); permanent "experimental" UI label; non-clinical disclaimer; rename UI label to "Playing Style Patterns" (pending U7) | Profile Agent |
| R29 | Engine pool + local LLM OOM on 16 GB machines | 4 | 4 | 16 | Lite / Standard / Full memory tiers selected at install time; orchestrator enforces tier budget with typed error | Engine Orch. |
| R30 | Naive 512-token chunking destroys book retrieval quality | 4 | 3 | 12 | Diagram-boundary-aware chunking is mandatory in chess-book ingest (see DB doc § A-F8) | KB / PDF Vision |
| R31 | Redis eviction policy collision corrupts agent message stream | 3 | 5 | 15 | Logical-DB separation: bus DB has `noeviction`, cache DB has `allkeys-lru`, separate Redis DBs / transports — see multi-agent doc addendum | DevOps |
