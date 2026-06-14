# CHESS COACH — Deep Project Audit & State Analysis Report

**Generated:** 2026-06-14 | **HEAD:** `6635ffa`

---

## A. Executive Summary

1. **Project is functional end-to-end** — gateway serves 10/11 routes at 200, 551 games imported, 3,739 training cards active, 150 PDF diagrams extracted via chessvision.ai
2. **Zero data quality issues** — 0 null FENs, 0 orphan positions, 0 orphan analyses across 25,948 positions
3. **Test coverage is critically low** — only 2/16 routes have tests (12.5%), no frontend tests at all
4. **Architecture is modular but incomplete** — 4 of 14 planned service modules are stubs
5. **chessvision.ai integration is the session breakthrough** — Phase 6 collapsed from 12 weeks (YOLOv8) to 2 hours (API call)

---

## B. Code Quality Assessment

### Backend (Python)

| Metric | Value |
|--------|-------|
| Total Python files | 71 |
| Total route files | 16 |
| Largest route | training_planner.py (239 lines, 3 functions) |
| Largest lib file | uci/engine.py (293 lines) |
| Module imports | 9/9 OK — no circular dependencies |
| Bare except: clauses | 0 |
| TODO/FIXME/HACK | 1 TODO in embedder.py |
| Routes with 0 try blocks | 7/16 |

### Frontend (TypeScript/React)

| Metric | Value |
|--------|-------|
| Total TS/TSX files | 227 |
| Coach panel files | 43 |
| Largest file | services/coach/api.ts (1,905 lines) |
| Hand-written fetch calls | 0 (all migrated to typed client) |
| Zustand usage in panels | 0 (Jotai only per ADR-0005) |
| i18n calls in panels | 0 |
| playerName hardcoding | Only in playerAtom.ts default value |

### Test Coverage

| Metric | Value |
|--------|-------|
| Test files | 10 |
| Route test coverage | 2/16 (12.5%) |
| Frontend tests | 0 |
| E2E tests | 0 |

---

## C. Architecture Reality Check

### Module Status (14 planned)

| Module | Status | Lines |
|--------|--------|-------|
| Gateway | Active | ~1,600 |
| Chess Analysis | Active | 293 |
| Engine Orchestrator | Active | 180 |
| Psychological Profile | Active | 214 |
| Training Planner | Active | 449 |
| Repertoire | Active | 250 |
| Narration | Active | 234 |
| Memory KB | Active | 276 |
| LLM Router | Active | 74 |
| PDF/Vision | Active | 189 |
| Jobs Queue | Stub | 0 |
| Analysis Service | Stub | 0 |
| Debug Agent | Stub | 0 |
| Synchronization | Stub | 0 |

**Score: 10/14 modules with real code (71%)**

### ADR Compliance: All 5 ADRs compliant

### En-Croissant Integration Surface Compliance: 95%

---

## D. Database Health

| Table | Rows |
|-------|------|
| positions | 25,948 |
| analyses | 24,962 |
| jobs | 25,397 |
| training_cards | 3,739 |
| analysis_cache | 7,594 |
| games | 551 |
| pdf_import_diagrams | 150 |
| narrations | 0 |
| repertoire_cache | 0 |

### Data Quality: Perfect

- 0 null move_san, 0 null FEN, 0 orphan positions, 0 orphan analyses
- 3,738/3,739 training cards due (99.7%) — likely FSRS bug

---

## E. Available Solutions Inventory

### Chess Engines
- Stockfish 18 at /usr/local/bin/stockfish
- lc0: Not installed
- Maia: Not installed (UCI-compatible via lc0)

### External APIs Working
- chessvision.ai /predict — no auth, valid FENs
- OpenRouter — configured
- Lichess API — working

### Key Python Packages
- fastapi 0.136.3, uvicorn 0.49.0, chess 1.11.2, torch 2.12.0+cpu
- sentence-transformers 5.5.1, qdrant-client 1.18.0, httpx 0.28.1
- opencv-python-headless 4.13.0, pdf2image 1.17.0, openai 2.41.0

---

## F. Top 5 Risks

1. **Test Coverage at 12.5%** — Only 2/16 routes tested
2. **7 Routes with No Error Handling** — Raw 500s on unhandled exceptions
3. **chessvision.ai No SLA** — Public endpoint, no uptime guarantee
4. **Narration Pipeline Not Writing to DB** — 0 rows in narrations table
5. **api.ts at 1,905 Lines** — Monolithic typed API client

---

## G. Recommended Next 3 Actions

1. Add error handling to 7 unprotected routes (2 hours)
2. Install lc0 + Maia weights (1 hour)
3. Add route tests for 5 most critical endpoints (3 hours)
