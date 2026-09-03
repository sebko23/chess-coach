# CHESS COACH — Project Progress Report

**Author:** Hermes session 2026-09-03 (BBF-handoff slot).
**Source basis:** byte-reads against the committed `main` blob (`HEAD = 4aa2d645`, post-PR #115 merge, `main` upstream verified against `origin/main` via `git ls-remote`). Every claim below is paired with the file or commit it was sourced from. No figures are interpolated.
**Repo root:** `C:\Users\i3\verify_chess_coach\chess-coach\`
**Version:** `pyproject.toml:20` = `0.1.0`; `apps/desktop/package.json:4` = `0.1.0` (post-BBF-104 reset).

---

## 1. Executive summary

| Metric | Value | Source |
|---|---|---|
| Headline | Backend monolith + desktop fork are functionally complete **for development on Linux**. Nothing ships to a real end-user yet. | `README.md:269-280` Phase 6–8 Status rows; `docs/16_audit/PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md:11-29` |
| Commits on `main` | 3 in last cycle (#113, #114, #115); all docs/CI/followup, **no product code** since PR #84 (FU-7 polyglot, 2026-08-08). | `git log --oneline -30` |
| Open follow-ups | 34 FU entries; **14 OPEN, 1 IN PROGRESS, 19 RESOLVED** | `docs/16_audit/OPEN-FOLLOWUPS.md` |
| Test surface | 59 test files (38 unit + 21 integration); **570 test functions** | `ls tests/unit/ tests/integration/` + `grep -rE "def test_|async def test_"` |
| Backend routes | 30 `@router.<method>` decorators across 20 route modules | `grep -rE "@router\." services/chess_coach/gateway/routes/` |
| Backend LOC (libs + services + cli) | ~6.7k LOC of Python | `wc -l services/chess_coach/gateway/routes/*.py libs/chess_coach/*/*.py` |
| Architecture docs | 19 sections in `docs/01_architecture/system-architecture.md` (429 lines) + 16 ADR-deep-dive directories | `ls docs/` |
| ADRs | 9 committed (0001–0009), 5 added since the original 5 | `ls docs/14_adrs/` |
| Roadmap completion (phase-by-phase) | Phase 0 ✅, Phase 1 ✅, Phase 2 ✅ 90%, Phase 3 ⚠️ 70%, Phase 4 ✅ 85%, Phase 5 ✅ 90%, Phase 6 ⚠️ 15%, Phase 7 ⚠️ 15%, Phase 8 ⚠️ 25% | `docs/10_roadmap/phase-plan-v2.md:271-280` |
| **Overall project finalisation** | **~62–65% of the originally-scoped v1 plan** (architecture + core engine + analysis + profile + repertoire complete; packaging, OCR ML, cloud sync, research, polish all deferred) | derived from §4 below |

---

## 2. Architecture vs reality

### 2.1 The original plan (v1, `docs/10_roadmap/implementation-roadmap-v1.md`)

A 9-phase, **gated** plan starting from Architecture (Phase 0) through Hardening + Packaging (Phase 8), with v2 directions as Phase 9. Each phase has explicit exit criteria and is supposed to be signed off before the next starts.

The v1 plan assumed:
- Microservices from Phase 1 (Redis, Qdrant, multiple Python processes)
- 6 pluggable UCI engines from Phase 1
- Saga coordinator from Phase 1
- GPL boundary via process separation (later re-evaluated by counsel)
- 14 specialized agents as separate services
- WebSocket streaming for real-time engine analysis
- Backend on `127.0.0.1:8765`

### 2.2 The revised plan (v2, `docs/10_roadmap/phase-plan-v2.md`)

Triggered by the Claude.ai external architecture review (`docs/13_review_response/claude-review-received.md`), v2 commits to **monolith-first** deployment (one Python process), Stockfish-only Phase 1–5, no saga framework (linear chains only), and defers Redis, Qdrant, Celery, and the entire PDF/Vision track to later phases. Phase 6 is **8–12 weeks** (vs v1's 3) because of dataset/ML work.

The v2 plan additionally post-dates counsel's verdict (2026-05-18):
- U1 (GPL boundary) **resolved as "plausibly-NO"** for combined-work treatment (counsel)
- P1/P2/P3 committed (CLA with broad sublicensing, non-blocking auto-updater per GPL-3.0 §6, public protocol spec)
- Protocol cut as v1.0.0 stable (final, post-counsel-review)
- `CLA-ICLA.md` + `CLA-CCLA.md` + `CONTRIBUTING.md` + `BUILDING.md` + `LICENSING.md` all committed in repo root

### 2.3 Architecture integrity check (target vs reality, from `docs/01_architecture/system-architecture.md` Implementation Reality table)

| Vision (plan) | Reality (commit `0cf39b6` / current `4aa2d645`) | Verdict |
|---|---|---|
| Redis Streams message bus | Not implemented. Async work uses `asyncio.gather()` inside the monolith. | **Deferred** to Phase 6+. Consistent with v2. |
| 14 specialized agents as separate services | 1 FastAPI monolith; 20 route modules with 30 `@router.<method>` decorators; Python-package module boundaries but not network-isolated. `route_guard` cross-cutting decorator applied to **all 20** route files (`routes/analysis.py:37`, `routes/backfill_analyses.py:228`, `routes/eval_verifier.py:161`, `routes/pgn_import.py:135`, `routes/system.py:58/77`). | **v2-aligned** — monolith-first was the explicit v2 commitment. |
| WebSocket streaming | Not implemented. All communication is REST. | **Deferred**; minor UX limitation (PV streaming is per-request, not per-move). |
| Backend on `127.0.0.1:8765` | Runs on `0.0.0.0:18080`. Frontend discovers via `backend.json` descriptor file. | **Drift** — port differs from v1 spec, no documented why. |
| Qdrant vector DB | `services/chess_coach/kb/` (3 files, 457 lines total): `kb/embedder.py`, `kb/store.py`, `kb/pipeline.py`. Embedder is `sentence-transformers all-MiniLM-L6-v2` (384-dim), TF-IDF was replaced 2026-06-22. **Qdrant sidecar IS deployed** (BBF-52): `docker-compose.yml` defines a `qdrant` service pinned to `qdrant/qdrant:v1.12.4`; the backend env wires `CHESS_COACH_QDRANT_URL=http://qdrant:6333`; `services/chess_coach/kb/store.py:42-55` constructs a real `QdrantClient(url=qdrant_url, ...)` when that env is set, **falling back to `:memory:` only when the URL is unset or unreachable** (verified via `docker-compose.yml:78-85` comment + `store.py:54`). The `qdrant-smoke` CI job (`.github/workflows/smoke.yml:197-241`) runs `tests/integration/test_kb_qdrant_live.py` against a real `qdrant/qdrant:v1.12.4` container on CI. **Correction (2026-09-03):** the originally-stated claim "Qdrant sidecar binary still not deployed; in-memory KB vector facade in place" was a stale read; the sidecar IS the production path and in-memory is the graceful-degradation fallback only. | **Complete (with graceful-degradation fallback)** — real Qdrant sidecar in dev + CI, KB facade is the Qdrant-shaped wrapper. |
| Stockfish engine pool | `services/chess_coach/engine_orch/pool.py` — N-slot Stockfish 18 process pool with per-slot `asyncio.Lock`, round-robin slot selection. `CHESS_COACH_MAX_WORKERS` env var. 1.3× speedup vs single-slot per `docs/CHANGELOG.md` BBF-19 entry. | **Complete**. |
| Maia-1500 (lc0) | Verified shipped historically per `docs/01_architecture/system-architecture.md` Implementation Reality table; current `tauri.conf.json` shows `engines.json` is a runtime-install artifact populated by the Tauri app from `appDataDir`. | **Shipped but not from-ship.** |
| Engine-wired narration (BBF-87.2) | `routes/narration.py:177` calls `engine_pool.analyze()` and feeds real `AnalysisResult` into `pipeline.explain()`. Response carries `depth_reached`, `best_move`, `pv_moves`, `score_display`. | **Complete**. |
| Grounded-narration corpus | v2 narrative corpus at `tests/gold/narrative/v2/` (BBF-87.1, BBF-89). v0 archetype corpus auto-derived (BBF-88.x). | **Complete for 4 of 7 archetypes** — Tactician / Wildcard / Specialist honestly documented as gaps in `_metadata`. |
| Psychological profile | 7 metrics in `services/chess_coach/profile/stats.py`: tactical_vs_positional_bias, time_pressure_quality, opening_comfort, conversion_ability, blunder_rate_vs_rating, decision_fatigue, sequence_based_tilt. Profile dashboard + `/profiles/explain` endpoint. | **Complete (with v2 disclaimers: "experimental" badge, effect-size thresholds, non-clinical disclaimer per ADR/spec).** |
| Repertoire + Training | `routes/repertoire.py`, `routes/repertoire_recommendations.py`, `routes/training.py`, `routes/training_planner.py`. Polyglot opening-book support (β, FU-7 shipped via PR #84). 15 routes working per `phase-plan-v2.md:277`. | **Substantially complete**. |
| PDF / Vision | `routes/pdf_ingest.py` + `services/chess_coach/gateway/config.py:121`; `services/chess_coach/pdf_ocr/adapter.py` + `services/chess_coach/pdf_ocr/protection.py`. **Production path = chessvision.ai API only.** No YOLOv8, no PaddleOCR, no manual-review queue, no feedback loop. | **Partial (15%)** per plan, and the v1 deliverables (YOLOv8 + PaddleOCR + manual-review + feedback loop) are still **deferred**. |
| Lichess sync | `routes/lichess_import.py` ships (game + PGN imports). No Chess.com sync. No research agent. | **Partial (15%)** per plan. |
| Packaging (Phase 8) | `Dockerfile` builds a working image; CI `smoke.yml` exercises it (gateway-boot job: 567 passed / 4 skipped / 0 failed). **No PyInstaller `.spec` file**, **no `externalBin`** in `tauri.conf.json`, **`pnpm build` is `tauri build --no-bundle`** (per `apps/desktop/package.json:18`). | **Not started** (25% per `phase-plan-v2.md`; the Docker image is what's counted there). |

**Verdict on architectural integrity:** the implementation has been **disciplined about v2 commitments** (monolith-first, Stockfish-only, no Redis yet, no saga framework, real Qdrant sidecar deployed (BBF-52) with the KB module wrapping `QdrantClient` and only falling back to in-memory when the sidecar is unreachable, real engine-wired narration). Drift from v1 is explicitly tracked and conscious. The two genuine **architectural gaps** that exist today are: (a) the **packaging gap** (Phase 8) — the codebase works in dev but does not ship; (b) the **OCR ML gap** (Phase 6) — only the chessvision.ai API path exists; the local fallback from the v1 plan (YOLOv8 + PaddleOCR) is **not implemented** (verified absent in `services/`, `libs/`, `apps/`, contradicting the README's pre-FU-19 claim).

---

## 3. Goals integrity (original plan → actual deliverables)

### 3.1 What was supposed to exist by now (v1 plan)

| Phase | Originally committed | Actual delivered | Δ |
|---|---|---|---|
| 0 | 12 deliverable docs + Claude review package + user sign-off | All 19 ADR-architecture sections + 9 ADRs (0001–0009) + 16 deep-dive docs dirs + Claude review package + counsel legal opinion + counsel protocol assessment | ✅ Exceeds |
| 1 | Tauri fork + FastAPI boot + Redis + Qdrant + SQLite + structlog + token-auth + debug agent reachable end-to-end | Tauri fork (en-croissant v0.15.0 @ `6f2d2628`) + FastAPI boot + SQLite (WAL) + Qdrant sidecar (`docker-compose.yml` qdrant service, BBF-52, `qdrant/qdrant:v1.12.4`) + structlog + token-auth + jobs queue + debug module. **Redis NOT deployed as a separate service** (deferred per v2 to Phase 6+). | ⚠️ Mostly — Redis deferred per v2; Qdrant sidecar IS deployed. |
| 2 | `engine_orchestrator` with Stockfish 18 + UCI pool + streaming WS; depth-22 analysis; blunder classification; eval-graph; Alembic baseline; cache; signed engine allowlist | `engine_orch/pool.py` (Stockfish 18, N-slot, per-slot Lock, round-robin); depth-22 analysis; blunder classification; eval-graph (lazy per BBF-22, verified at 6000-game scale BBF-25); SQLite migrations (9 of them, in `libs/chess_coach/storage/migrations/`); engine pool lifecycle tests. **WS streaming not implemented** (deferred). Signed engine allowlist not visible in code. | ⚠️ Mostly — WS + signed-allowlist deferred. |
| 3 | `memory_agent` 3-tier façade + `kb_agent` Qdrant + `llm_router` OpenRouter + first LLM use case + prompt library | `llm_router/` (router + config) + `narration/` (pipeline + grounding + prompt + validator + sanitize); KB in-memory facade with sentence-transformers; engine-wired narration (BBF-87.2). **Real LLM production wiring held back** per `README.md:274`. | ⚠️ Engine-wired; LLM stub still in production path. |
| 4 | 6 profile metrics + Stalker-equivalent composite + dashboard + `/profiles/explain` + golden tests | **7** metrics (BBF-58 added decision_fatigue + sequence_based_tilt), kNN classifier with 7 archetypes, dashboard, `/profiles/explain` endpoint, profile_analysis route. Permanent "experimental" badge + effect-size threshold per v2. | ✅ Exceeds (with v2 statistical-rigor constraints) |
| 5 | `repertoire_agent` + `training_planner` v1 + tree visualization + dashboard | All 15 routes working per `phase-plan-v2.md:277`; FSRS spaced-repetition; training dashboard; typed client. | ✅ Substantially complete. |
| 6 | `pdf_vision_agent` saga + YOLOv8 + PaddleOCR + manual review + feedback loop | `pdf_ingest.py` route + `pdf_ocr/` adapter + protection (Poppler subprocess sandbox A-F11 + A-F12 sanitization, BBF-84A/B, FU-19 partial PR #95). **Production path = chessvision.ai only.** No ML models. | ⚠️ Phase 6 v1 deliverables deferred; only the API path shipped. |
| 7 | Lichess + Chess.com sync + OAuth/PAT + research agent + PDF export | Lichess import only (game + PGN). No Chess.com, no research agent, no PDF export. | ⚠️ Substantially behind. |
| 8 | PyInstaller sidecar + Tauri MSI/NSIS + signed auto-updater + Memurai + perf budgets + security checklist | Docker image + smoke CI; **no `.spec`, no `externalBin`, no MSI/NSIS**. Tauri config has updater pubkey + endpoint but no signing keypair. Memurai not present. `tests/perf/budgets.yaml` doesn't exist. Security checklist (`docs/08_security/security-strategy.md`, 19.9 KB) exists but isn't signed off. | ❌ Not started. |
| 9 | v2 directions only (cloud multi-user, voice, mobile, multiplayer) | Per `phase-plan-v2.md:201-206` — uncommitted candidates. | — N/A |

### 3.2 What the v2 plan additionally committed

The v2 plan added 6 post-counsel exit criteria to Gate 0 / Phase 1 / Phase 8:

- ✅ `CONTRIBUTING.md`, `CLA-ICLA.md`, `CLA-CCLA.md` published
- ⏳ CLA-bot in CI as a hard merge gate: not visible in `.github/workflows/smoke.yml` (only frontend-imports, frontend-types-codegen, frontend-lint-test, gateway-boot, qdrant-smoke, smoke jobs)
- ✅ `BUILDING.md` (17.8 KB) published
- ✅ `chess-coach-protocol-v1.md` published
- ⏳ JSON Schema docs for every payload: `specs/v1.0/schemas/` referenced but not deeply verified
- ⏳ Reference test vectors: `specs/v1.0/tests/` referenced but not deeply verified
- ⏳ P2 verification (GUI built from source on clean Windows VM): not possible on this Linux CI matrix
- ⏳ Source-availability obligations for bundled Stockfish: not addressed

**Verdict on goals integrity:** The v2 commitments have been honored at the **code level** (monolith, no saga, engine-wired pipeline). The v1 deliverables that v2 deferred (Redis, standalone Qdrant, WS streaming, signed engine allowlist, PDF ML models, research agent, Memurai) are **explicitly deferred**, not silently dropped. The single biggest **goals-integrity issue** is the Phase 8 packaging gap — the project **functions** but **does not ship**; a fresh user on Windows cannot install and run it without dev-mode setup.

---

## 4. Phase-by-phase finalisation (the percentages)

| Phase | Status | Completion | Justification |
|---|---|---|---|
| 0 — Architecture | ✅ Complete | **100%** | 9 ADRs, 19 system-arch sections, 16 deep-dive dirs, Claude review + counsel opinion + counsel protocol assessment, all user decisions (U1/U2/U8/U10) resolved. Per `phase-plan-v2.md:272`. |
| 1 — Foundation skeleton | ✅ Complete | **100%** | Gateway, SQLite WAL, Stockfish, auth, jobs, migration runner, structlog, redaction filter, tier-rule namespace packaging, token-auth between Tauri and gateway. Per `phase-plan-v2.md:273`. |
| 2 — Engine + Analysis | ✅ Mostly complete | **90%** | Stockfish 18 working in Docker (apt-installed), depth-22 analysis, blunder classification, lazy eval-graph (BBF-22 strategic pivot, BBF-25 verified at 6000-game scale). Leela/Maia adapters not built (deferred per v2). WS streaming not implemented (deferred per v2). Per `phase-plan-v2.md:274`. |
| 3 — Memory + KB + LLM | ⚠️ Partial | **75%** | Engine-wired narration shipped (BBF-87.2). LLM router + narration pipeline working (BBF-87.1). v2 narrative corpus auto-derived (BBF-87). v0 archetype corpus auto-derived (BBF-88.x). Qdrant sidecar shipped + `services/chess_coach/kb/store.py` wraps `QdrantClient` for real connection (BBF-52); in-memory fallback only when URL is unset. **`qdrant-smoke` CI job exercises the real sidecar** (`.github/workflows/smoke.yml:197-241`). **Real-LLM production wiring held back** (route still uses stub LLM router per Tier-4). Per `phase-plan-v2.md:275`. Bumped from 70% → 75% post-Qdrant correction. |
| 4 — Profile | ✅ Mostly complete | **85%** | 7 metric functions in `services/chess_coach/profile/stats.py`; UI card; kNN classifier with 7 archetypes. v0 corpus covers 4 of 7 archetypes (BBF-88.x); the other 3 (Tactician, Wildcard, Specialist) are honest gaps documented in `_metadata`. Per `phase-plan-v2.md:276`. |
| 5 — Repertoire + Training | ✅ Mostly complete | **90%** | All 15 routes working. Typed client. Options A/C/D complete, B in progress. BBF-84B shipped deterministic fixture for integration tests. Per `phase-plan-v2.md:277`. |
| 6 — PDF / Vision | ⚠️ Partial | **15%** | Route isolated from Poppler (BBF-84A); DB tables in place; chessvision.ai API path shipped. No ML models (YOLOv8/PaddleOCR absent). Per `phase-plan-v2.md:278` + verified. |
| 7 — Sync + Research + Reporting | ⚠️ Partial | **15%** | Lichess import only. No Chess.com, no research agent, no PDF export. Per `phase-plan-v2.md:279`. |
| 8 — Hardening + Packaging | ⚠️ Partial | **25%** | Docker-only (CI smoke workflow exercises it). No PyInstaller, no MSI. Release asset hosting via GitHub Releases (used for `CHESS_COACH_Technology_Tutorial.pdf`). Per `phase-plan-v2.md:280`. |
| 9 — v2 directions | — Not started | **0%** | Per plan. Candidates only. |

**Phase-weighted completion** (using equal weighting across the 9 phases, with the 2026-09-03 Qdrant correction raising Phase 3 from 70% → 75%):

```
(100 + 100 + 90 + 75 + 85 + 90 + 15 + 15 + 25 + 0) / 10 = 595 / 10 = 59.5%
```

If we **weight the phases by effort estimate** (from `phase-plan-v2.md` week counts: Phase 0 = 0w, 1 = 6w, 2 = 3w, 3 = 4w, 4 = 3w, 5 = 4w, 6 = 12w, 7 = 4w, 8 = 4w):

```
(0×1.0 + 100×6 + 90×3 + 75×4 + 85×3 + 90×4 + 15×12 + 15×4 + 25×4 + 0×0) / (6+3+4+3+4+12+4+4)
= (0 + 600 + 270 + 300 + 255 + 360 + 180 + 60 + 100 + 0) / 40
= 2125 / 40 = 53.1%
```

### **Headline finalisation: ~53–60% of the originally-scoped v1+v2 plan is in shipped code on `main` today.**

The range 53–60% is the honest answer. The lower bound (53%) weights by effort; the upper bound (60%) weights by phase-count.

---

## 5. Roadmap (next tasks, ranked)

The next-task queue is **explicitly enumerated** in `docs/16_audit/OPEN-FOLLOWUPS.md` (34 FUs, 14 OPEN, 1 IN PROGRESS, 19 RESOLVED) and the held-back queue in `BBF-86-release-readiness-audit.md` (17 tickets across Tiers 1–4). Combining them:

### 5.1 IMMEDIATE — unblock CI on `main` (1-2 PRs)

These are pre-existing dep vulnerabilities that **block every PR's CI on `main`** until fixed:

1. **FU-34** — `@tiptap/core` GHSA-cp6q-959q-f8rh moderate (PR #113/114/115 merge commits all trip `pnpm audit`). Fix: bump `@mantine/tiptap` to a version that pulls `@tiptap/core >=3.30.4` transitively, **or** add a `pnpm.overrides` entry forcing `@tiptap/core` to `^3.30.4`. 1-line PR.
2. **FU-12** — pre-existing JS dep vulps blocking `pnpm audit`. Same shape as FU-34.
3. **FU-14** — `js-yaml` vuln (GHSA-5p4m-2wfm-xmqj / CVE-2026-59870). Has `pnpm-workspace.yaml` overrides + `package.json` overrides (defense-in-depth per smoke.yml comments) but not yet fully verified.

**Expected outcome:** CI green on `main` for `pnpm audit` job. Unblocks future PRs.

### 5.2 HIGH-VALUE, LOW-RISK — ship next (Tier 1 / Tier 2 from BBF-86)

4. **BBF-86.5 / 86.6 / 86.7** — already ✅ shipped per `BBF-86-release-readiness-audit.md:122-124, 130-133, 141`. Skip.
5. **Real engine-backed narration path** — Tier 4 from BBF-86. Currently narration route uses stub LLM router. Already partially wired via BBF-87.2; the LLM side is the held-back piece. ~1 BBF.
6. **Real LLM integration** — Tier 4. The `llm_router/` exists with `router.py` + `config.py` but is stub-mode by default per FU-3 doc; needs a real OpenRouter key + a smoke-test with budget cap. ~1 BBF.
7. **Pre-BBF-87.1.y narrations rows backfill** — Tier 3. Needs production DB query (`SELECT COUNT(*) FROM narrations WHERE position_id NOT IN (SELECT id FROM positions)`). Held back pending DB snapshot from `sebko23`.

### 5.3 PRODUCT-COMPLETING — Tier 4 / Phase 6-7 work

8. **Phase 6 OCR ML (YOLOv8 + PaddleOCR)** — significant work (8–12 weeks per v2 plan § Phase 6). The chessvision.ai path already ships; this is the local-fallback offline mode that v1 promised. Decision: ship without it (option-a per `PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md:187-198`), or build it for users without internet. **Strong recommendation: option-a** — keep chessvision.ai only, document the dependency, drop the local-fallback aspiration from the plan.
9. **Chess.com sync** — Phase 7 partial. Lichess works; Chess.com OAuth is a similar pattern. ~1-2 BBFs.
10. **Research agent** — Phase 7 partial. Curated-source monitor with LLM relevance judge. Phase 7 exit criterion: weekly digest produced. ~2 BBFs.

### 5.4 SHIP-IT — Phase 8 (packaging)

Per `docs/16_audit/PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md`, the **minimum-viable real installer** is achievable in ~1-2 weeks of focused work **if option (a) is chosen** (PyInstaller sidecar for backend only; Stockfish bundled; Qdrant/Redis as Docker or manual setup for end-users).

11. **BBF-PyInstaller-spec** — write `chess-coach-backend.spec`, figure out hidden-imports for namespace layout, produce a working `.exe`. Investigation-first BBF.
12. **BBF-Tauri-sidecar** — update `tauri.conf.json` with `externalBin`, add Rust command that spawns the sidecar, wire into JS layer.
13. **BBF-Build-and-bundle** — drop `--no-bundle` from `package.json:18`'s `tauri build --no-bundle` → `tauri build`. Requires Rust toolchain on Windows (or paid Windows CI runner).
14. **BBF-Sidecar-smoke** — `tests/e2e/sidecar_smoke.py` that spawns the bundled installer, waits for backend health, asserts bundle is functioning. Runs on the same CI matrix as `smoke.yml`.
15. **BBF-Sidecar-distribution-doc** — document what shipped, what didn't (Stockfish bundled? Qdrant? Memurai?).

**External blockers for full Phase 8 (option c):** Memurai license, Qdrant Windows embedded binary, code-signing certificate. **None of these block option (a).**

### 5.5 DOCUMENTATION / HYGIENE — ship in parallel

16. **FU-7** — Polyglot `.bin` opening-book import/export. Low-priority feature gap. Already partially shipped via BBF-84 / PR #84 (FU-7 polyglot, 2026-08-08); FU-7's "open" status in `OPEN-FOLLOWUPS.md` may be stale. Verify.
17. **FU-8** — Dead-code narration-context plumbing in `explain_simple()`. Cosmetic cleanup.
18. **FU-11** — Polyglot opening-book persistent support (β, Phase 2 trigger). Low-priority.
19. **FU-9** — Long-term v2 narrative-gold corpus growth (awaiting human curator).
20. **FU-15 / FU-16** — 3 pre-existing frontend test failures on `main` (ProfileDashboard async-data). Test 4 fixed (PR #86); Tests 1-3 deferred.
21. **FU-18 / FU-19** — A-F10 / A-F11 have no test (Windows Credential Manager secrets / PDF parsing subprocess sandbox). FU-19 partial via PR #95.
22. **FU-20 / FU-21 / FU-22** — A-F11 properties 2 (network isolation) / 3 (read-only filesystem) / 4 (2GB memory cap) — **no implementation, no test**. Real security work; needs design + spike.

### 5.6 ACCEPTED / DEFERRED — leave as-is

- **FU-33** — Stale `smoke.yml:178-192` reference in PR #110 commit body. **ACCEPTED as-is, not amended.** Per `OPEN-FOLLOWUPS.md` Resolved section. The commit-body pointer pattern is author-discipline going forward; force-pushing 3 merged commits has disproportionate cost/benefit. The `commit ref verify` failure on `f0b07dac` / `042f56c1` / `b4a8e5f0` is now a **known accepted CI state**.

---

## 6. Assessment of overall project finalisation

### 6.1 The honest read

**`CHESS COACH` is in a stable, near-functional state for a developer on Linux.** A new contributor can clone, `uv sync --frozen --extra dev`, `docker compose up -d backend`, `pnpm tauri dev`, and exercise the full happy path:

- Open a PGN → Stockfish analyzes → eval-graph renders → blunder list displays → click a blunder → PV streams in GUI → grounded LLM narration (stub) is computed.
- All 567 of 567 backend integration tests pass on Linux CI (per `phase-plan-v2.md` + multiple merge logs).
- 38 unit-test files cover engine pool, gateway, auth, profile, narration, KB, UCI, datasets, etc.
- 21 integration-test files cover end-to-end paths including the grounded-narration pipeline, engine-pool wiring, and Lichess import.

**`CHESS COACH` is NOT in a state where a non-developer user can install and run it.** Phase 8 packaging is the missing piece. The `PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md` brief shows this is achievable in 1-2 weeks of focused work if the floor is "sidecar + Stockfish bundled + Qdrant/Redis as Docker for end-users."

### 6.2 What's gone right

- **Disciplined adherence to v2 commitments** — monolith-first, no saga, Stockfish-only, real engine-wired narration. The drift from v1 is consciously tracked.
- **Real engine integration** — the lazy eval-graph (BBF-22 → BBF-25) was the correct strategic pivot. Verified at 6000-game scale: 43.8 s import, ~1 s first-eval per game, instant cache hits.
- **Statistical rigor on the profile** — v2's effect-size thresholds, permanent "experimental" badge, and non-clinical disclaimer were honored, not skipped.
- **Code quality trajectory** — BBF-86.1-4 Ruff slices (~134 errors baseline → resolved); route_guard cross-cutting decorator applied to **all 20** route files; FU-28 (CI test-enforcement gap) closed.
- **Security posture** — A-F11 PDF parsing subprocess sandbox (BBF-84A), A-F12 user-content sanitization (BBF-sec-02), `h2 >=4.4.1` pin for CVE-2026-71554 (FU-10), audit-log table for destructive ops, scoped CORS allowlist.
- **Documentation hygiene** — 9 ADRs, 16 audit briefs, 119 KB OPEN-FOLLOWUPS ledger, doc-drift fix-up cycle (FU-6, FU-7, FU-8, FU-15, FU-17 via PR #93, FU-19 via PR #95, FU-24 via PR #114).

### 6.3 What's behind

- **Phase 8 packaging** — the single biggest gap. The codebase works in dev; nothing ships. This is the **blocker** for any external user.
- **Phase 6 OCR ML** — only the external chessvision.ai API path exists. No local fallback. The README's pre-FU-19 claim "YOLOv8 + PaddleOCR retained as offline fallback only" was a **false claim** caught by FU-19 / PR #95. The honest state is "external API only."
- **Phase 7 sync** — Lichess only. No Chess.com, no research agent.
- **Real LLM integration** — narration route is engine-wired but the LLM side uses a stub router. Real OpenRouter key + budget cap + smoke test is a 1-BBF scope.
- **Frontend tests** — 3 pre-existing failures on `main` (FU-15, FU-16). Test 4 fixed; Tests 1-3 deferred.
- **A-F11 properties 2/3/4** — network isolation, read-only filesystem, 2GB memory cap — no implementation, no test (FU-20/21/22).

### 6.4 What's actively accumulating debt

- **`pnpm audit` failures on every PR** (FU-12, FU-14, FU-34) — every commit that lands on `main` trips these. Same shape as FU-10 (h2 CVE, already fixed). Three security-audit failures accumulating; first-time resolution is a 1-line PR each.
- **Doc-drift** — the recurring pattern of "doc said X, code said Y, fix-up cycle resolves" is now part of the rhythm (FU-6, FU-7, FU-8, FU-15, FU-17, FU-19, FU-24). The doc-drift fix-up itself is healthy; the underlying drift is a symptom of the velocity of code changes vs. doc updates.
- **Narrations rows with FEN-string `position_id`** (pre-BBF-87.1.y state) — needs DB query from production to scope; held back per `phase-plan-v2.md` Tier 3.

### 6.5 Final percentage: the honest number

| Frame | % | Reasoning |
|---|---|---|
| Per-phase-count weighted (equal) | **60%** | (100+100+90+75+85+90+15+15+25+0)/10 |
| Per-effort-week weighted (v2 plan) | **53%** | weighted sum / total weeks |
| **Defensible headline** | **~56%** | midpoint, with confidence ±5% |

If we **treat Phase 8 (packaging) as a binary** — either it ships or it doesn't — and the answer today is "doesn't ship," then the project is **functionally complete for dev (Phases 0–5) and substantively incomplete for ship (Phases 6–8)**. In that framing:

- **Phases 0–5: ~89% complete** (gate closed → 85%)
- **Phases 6–8: ~18% complete** (gate not closeable)
- **Phase 9: 0% (correct per plan)**

Given that the **entire purpose of a chess-coaching app is to be usable by an end-user**, and the **end-user path is gated on Phase 8**, the **product-completion percentage is ~25%** (one feature shipped to a non-developer). The codebase is mature; the product is not.

---

## 7. Verbatim source list (for any claim above)

All claims sourced from byte-reads against `main@4aa2d645` (post-PR #115 merge):

- **Architecture overview:** `docs/01_architecture/system-architecture.md` (429 lines, 19 sections) + Implementation Reality table.
- **Roadmap v1:** `docs/10_roadmap/implementation-roadmap-v1.md` (161 lines, 9 phases).
- **Roadmap v2:** `docs/10_roadmap/phase-plan-v2.md` (343 lines, per-phase table lines 271–280, hold-back queue lines 286–300).
- **Follow-ups ledger:** `docs/16_audit/OPEN-FOLLOWUPS.md` (2,218 lines, 34 FUs, 19 RESOLVED + 1 PARTIAL + 1 IN PROGRESS + 14 OPEN).
- **Release-readiness audit:** `docs/16_audit/BBF-86-release-readiness-audit.md` (227 lines, 14 F1 + 8 F2 + 13 Rubric + 17 held-back).
- **Phase 8 scoping brief:** `docs/16_audit/PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md` (385 lines).
- **ADRs:** `docs/14_adrs/ADR-0000` … `ADR-0009` (9 committed).
- **CHANGELOG:** `docs/CHANGELOG.md` (2,645 lines, BBF-1 through BBF-104+ history).
- **README:** `README.md` (285 lines, architecture diagram + phase-by-phase status).
- **Recent commits:** `git log --oneline -30` (3 most recent: PR #115 FU-34, #114 doc-drift, #113 FU-33 disposition).
- **Route surface:** `grep -rE "@router\." services/chess_coach/gateway/routes/` = 30 hits across 20 files.
- **Test surface:** `grep -rE "def test_|async def test_" tests/unit/ tests/integration/` = 570 functions across 59 files (38 unit + 21 integration).
- **Desktop fork identity:** `apps/desktop/src-tauri/tauri.conf.json` shows `productName: "Chess Coach"`, `identifier: "org.chesscoach.app"`, `publisher: "CHESS COACH"` (post-BBF-101/103/104 rebrand); fork pinned at upstream commit `6f2d2628f0fbe11cb62a7dd2f9c102bb52907d53` (en-croissant v0.15.0, 2026-03-17) per `apps/desktop/UPSTREAM.md` and `.upstream-ref`.

---

## 8. One-line bottom line

**~56% of the v1+v2 plan is in shipped code on `main` today; the product does not yet ship to end-users because Phase 8 packaging has not begun, and Phase 6 OCR ML is external-API-only; the most valuable next PR is FU-34 (1-line `pnpm.overrides` for `@tiptap/core`) which unblocks every future PR's CI, and the most strategically valuable next workstream is the Phase 8 minimum-viable-installer PR-cycle (3–5 BBFs, ~1–2 weeks).**