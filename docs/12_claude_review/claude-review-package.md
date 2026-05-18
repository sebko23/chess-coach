# CHESS COACH — External Review Package (for Claude.ai)

**Audience**: an external LLM reviewer (Claude.ai) sanity-checking the Phase-1 architecture before implementation begins.
**Goal**: get critical pushback on decisions, hidden risks, scaling concerns, and viable alternatives. **This is not a pitch.** Be skeptical.
**Conventions**: "we" = the planning agent (Agent Zero) + user. Sections are deliberately short; deeper context is one file away.

---

## 1. One-paragraph project summary

CHESS COACH is a single-user, local-first, grandmaster-level autonomous chess coaching desktop application for Windows. It forks the en-croissant chess GUI (Tauri + React + Mantine + chessground) and adds a Python multi-agent backend (14 specialized agents) that runs in Docker for dev and as a PyInstaller sidecar for end users. Core capabilities: multi-engine analysis (Stockfish 18, Leela, Maia, Berserk, Komodo, Ethereal), psychological/behavioral profiling, opening repertoire intelligence, adaptive training plans (FSRS), PDF book ingest with chess-diagram → FEN reconstruction (YOLOv8 + piece classifier + PaddleOCR), a long-term memory tier (SQLite + Qdrant + markdown skills), and an OpenRouter-mediated LLM layer used surgically for narration, summarization, and prose reasoning rather than as the main control loop.

---

## 2. Critical decisions (and their justifications, briefly)

| # | Decision | Justification (short) | Trade-off accepted |
|---|---|---|---|
| D1 | **Tauri 2.x** as desktop shell | en-croissant is already Tauri; switching shells means abandoning the en-croissant GUI we must preserve. Better resource posture than Electron. | Rust learning curve in shell code; we mitigate by keeping shell commands thin. |
| D2 | **Fork from a pinned en-croissant tag**, code we author lives only in `panels/coach/*` and a few integration points | en-croissant ships fast (~800 PRs, last commit very recent); diverging across the codebase makes rebases unbearable. | Constrained UI integration surface. |
| D3 | **GPL boundary = process boundary** | en-croissant is GPL-3.0-only; our backend agents are separate processes, communicating only over documented HTTP/WS. | We need to honor process separation rigorously — no Rust-side linking to en-croissant code from our backend wrappers. |
| D4 | **Python 3.11 backend** with FastAPI | Best ML/AI/chess library ecosystem; async-first; auto-OpenAPI. | Slower than Go/Rust; hot paths (engines) are external processes anyway. |
| D5 | **14 specialized agents** with **tier-rule dependency graph** | Prevents the monolithic-LLM-loop antipattern and architectural drift; clear debuggability. | Higher initial complexity; mitigated by a CI linter enforcing tier rules. |
| D6 | **Redis Streams as agent bus** | Already required for Celery + cache; durable, replayable, consumer-group capable; no extra infra. | Not a full event-sourcing platform; sufficient for our scale. |
| D7 | **SQLite (WAL) as primary store, Postgres as future upgrade** | Zero-admin for end users; portable backups (copy a file). | Single-writer; mitigated by a `db_writer` actor pattern. |
| D8 | **Qdrant as vector DB** | Embedded mode in Rust, small footprint, Apache-2.0, snapshot/promote path. | Less brand-name than Chroma, but more production-stable. |
| D9 | **LLM Router library** (in-process, not a service) as the **sole** ingress for LLM calls | Centralizes budget, caching, fallback, structured-output validation, prompt-injection containment. | One library imported many places; we accept the coupling because the alternative is per-agent ad-hoc LLM use. |
| D10 | **LLMs used surgically, not agentically** | Cost control, determinism for chess-mathematical work, testability. | Less impressive demos; we view this as a feature. |
| D11 | **PyInstaller sidecar** for end-user backend (Docker only for dev) | Avoids forcing Docker Desktop on end users. | Larger installer; binary signing required. |
| D12 | **Monorepo with workspace boundaries** | Atomic cross-cutting refactors; single CI; license enforced by directory + `LICENSING.md`. | Slower CI on touch-everything changes; mitigated by path-filtered triggers. |
| D13 | **Confidence intervals on all profile metrics**, "experimental" label below sample-size threshold | Psychological profiling is easy to over-claim; we want explainability and humility built in. | Slightly heavier UI; this is correct. |
| D14 | **Engine cache keyed by (fen, engine_id, engine_version, depth, multipv, settings_hash)** | Silent cache poisoning on engine upgrade is a known industry footgun. | Cache miss after upgrade; acceptable. |
| D15 | **OS keychain (Windows Credential Manager) for secrets**, no plaintext `.env` outside dev mode | Process-inspection and accidental commit are realistic threats. | One Windows-platform dep; cross-platform later. |

---

## 3. Unresolved risks / open questions (please pressure-test)

1. **GPL boundary robustness.** Is our "separate-process + documented HTTP/WS protocol" boundary actually sufficient under GPL-3.0? Are there edge cases (e.g. shipping the backend binary in the same MSI installer as the GUI) that compromise it? If we ship one installer that drops both an en-croissant-derived `.exe` and our backend `.exe`, does that constitute distribution as a single combined work?
2. **FEN reconstruction accuracy.** YOLOv8 + a custom piece-classifier CNN on diverse chess-book stylistics is non-trivial. Is the pipeline plausible? What pre-existing datasets/models should we evaluate before training from scratch?
3. **Psychological profiling validity.** ChessStalker's methodology is closed-source and our metrics are heuristic-statistical. How do we guard against the metric-as-narrative trap — where users (and we) interpret noise as signal? Is confidence-banding + sample-size gating sufficient, or do we need formal statistical tests baked into each metric?
4. **Tier-rule linter sustainability.** We propose enforcing dependency tiers via a custom linter. In practice, when one agent legitimately needs to call another at "the wrong tier", will the team route through events as designed, or will the rule erode? Is there a better encoding (e.g. import-time enforcement via package boundaries)?
5. **End-user Redis story on Windows.** We propose Memurai (Redis-compatible) as a bundled service. Memurai's licensing for redistribution + its long-term maintenance are non-trivial. Alternatives we've considered: WSL2 dependency (unacceptable UX cost), KeyDB on Windows (less mature), in-process replacement (loses Celery and bus). Better options?
6. **Engine pool memory.** Stockfish at 1 GB hash × pool size × (multiple engines installed) could hit RAM ceilings on 16 GB machines while a user also wants Leela GPU + a local LLM. Is dynamic hash sizing the right escape hatch, or do we need a hard scheduler that pauses lower-priority engines?
7. **OpenRouter as primary LLM provider.** Single-vendor dependency for a coaching tool that the user pays per-call for. Is our fallback chain (OpenRouter → direct OpenAI/Anthropic → Ollama) realistic, especially given different prompt-formatting and tool-use quirks per provider?
8. **SQLite at scale.** A serious player + book library + engine analyses could push the database into the multi-GB range. WAL + mmap + indexes should hold, but we have no real-world data point. Should we benchmark earlier (Phase 2) rather than later?
9. **Saga without a real saga framework.** We design P5 (saga) on top of Redis Streams + a small SQLite-backed coordinator. Are we under-estimating the cost of building this versus adopting (e.g.) Temporal or Dapr? Our take: yes for the simpler sagas, no if sagas grow beyond ~3 steps.
10. **Auto-update for a GPL fork.** Distributing signed updates of a GPL-3.0 binary to end users: any practical pitfalls (corresponding source delivery, update key rotation under GPL §6)?

---

## 4. Scaling concerns we are aware of

- **Vector DB growth.** Per-book embedding cost is real; a serious library (200+ books) produces ~100k–500k vectors. Qdrant handles this with mmap segments above ~100k per collection. Embedding throughput is the bottleneck during ingest, not query time.
- **SQLite write contention.** Mitigated by the `db_writer` actor and bulk-import on a separate connection. If contention persists in real workloads, the Postgres upgrade path is documented.
- **Engine concurrency vs CPU.** Default pool = (cores ÷ 2). Multi-engine comparisons can saturate quickly; a per-request budget prevents runaway.
- **LLM cost.** Per-task daily budgets, prompt cache, downgrade-on-budget-low. Worst-case we burn the daily budget and gracefully degrade.
- **Single-user only.** Multi-user (club server) is explicitly out of scope for v1; the architecture (Redis bus, Postgres path, separate-process services) does not preclude it but doesn't pay for it either.

---

## 5. Alternatives we considered and rejected (please challenge our rejections)

| Rejected option | Why we rejected | Counter-argument we want you to make if applicable |
|---|---|---|
| Electron desktop shell | en-croissant is Tauri; resource overhead higher | Is en-croissant's value really worth this constraint? |
| Pure-LLM agentic main loop (LangGraph / autogen-style) | Cost, non-determinism, testability | What would we lose by being too deterministic? |
| LangChain | Heavyweight, unstable API surface | Are there parts (e.g. prompt templates, output parsers) we are reinventing for no reason? |
| Chroma vector DB | Production-stability concerns in 0.4.x | Has 0.5+ resolved this enough to reconsider? |
| pgvector | Couples to Postgres which we don't want as a hard dep | If we end up needing Postgres anyway (multi-user later), is unifying around pgvector simpler? |
| Direct UCI engine integration in Tauri/Rust | Want to keep engine orchestration hot-reloadable in Python | We pay a process-hop cost; significant? |
| Polyrepo per service | Atomic refactors and shared types are easier in monorepo | At what team size does the monorepo crack? |
| MongoDB / schema-on-read | Wrong tradeoff for a well-known chess data model | Are there parts (e.g. lesson content) where flexibility would help? |
| Voice coaching in v1 | Scope explosion; non-trivial latency budget | Are we under-valuing the coaching UX it would enable? |

---

## 6. Areas where we explicitly want external validation

1. **License interpretation** (item 1 above). Not legal advice — but: does an MSI installer that drops two `.exe` files (GUI = GPL, backend = Apache) constitute a single combined work, or are they aggregate? Reasoning, not verdict.
2. **Psychological profiling rigor.** Is our explainability + confidence-band approach sufficient, or do we need formal hypothesis tests per metric to avoid misleading users?
3. **The 14-module count.** Too many? Too few? Are any two modules ripe for merging (e.g. Memory + KB)? Are any single modules secretly two responsibilities (e.g. Training Planner = lesson generation + scheduling)?
4. **Saga vs alternatives.** Should we adopt a battle-tested saga/workflow framework now (Temporal, Dapr Workflows, Prefect) rather than building atop Redis Streams + SQLite?
5. **LLM Router as a library vs a service.** We chose library to avoid an extra hop on every LLM call. The cost: every importer gets the dep tree and a shared rate-limiter must coordinate via Redis. Service-based router has a clean ingress and easier observability. Which trades better at our scale?
6. **Engine cache invalidation.** Is the `(fen, engine_id, engine_version, depth, multipv, settings_hash)` key sufficient, or are there UCI options/network/hardware variations that produce different results on identical settings?
7. **Phase-6 (PDF/Vision) ambition.** Is FEN reconstruction at useful accuracy realistic in the timeline we propose (3 weeks), or are we under-budgeting? Concretely: target accuracy threshold for the gate?

---

## 7. What we are NOT asking you to do

- Write code. No code yet by design.
- Re-pick the desktop shell. The en-croissant preservation requirement makes Tauri effectively pre-determined; flagging this as a problem is fine but proposing Electron without addressing en-croissant compatibility isn't useful.
- Propose adding multi-user / cloud features to v1. Explicitly deferred to Phase 9 candidates.
- Recommend voice coaching for v1. Explicitly deferred.

---

## 8. File map for deeper reading

If you want to drill into anything above:

- Master integrative doc: `docs/01_architecture/system-architecture.md`
- 14-module specs: `docs/02_modules/module-decomposition.md`
- Stack with rejections: `docs/03_technology/technology-comparison.md`
- DB decision: `docs/04_database/database-decision.md`
- Desktop shell decision: `docs/05_desktop_shell/desktop-shell-decision.md`
- Multi-agent + bus + tier rules: `docs/06_multi_agent/multi-agent-workflow.md`
- Risk register: `docs/07_risk/risk-analysis.md`
- Security: `docs/08_security/security-strategy.md`
- Performance budgets: `docs/09_performance/performance-strategy.md`
- Roadmap (9 phases with gate criteria): `docs/10_roadmap/implementation-roadmap.md`
- Repo structure + license posture: `docs/11_repo_structure/repository-structure.md`
- Raw research: `docs/research/en-croissant-analysis.md`, `docs/research/chessstalker-concepts.md`

---

## 9. The specific question, if you only have time for one

**"What is the single architectural decision in this package that is most likely to cause us the most pain in 6 months, and why?"**
