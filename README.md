# CHESS COACH

**Grandmaster-level autonomous chess coaching platform.**

## Project Status

**Phase 1 — Architecture Analysis: ✅ COMPLETE.**
**External (Claude.ai) review: ✅ RECEIVED AND INTEGRATED (2026-05-18).**
**Implementation: ⛔ BLOCKED on user decision U1 (GPL license boundary).**

See `docs/13_review_response/response-to-review.md` for the full point-by-point response and `docs/10_roadmap/phase-plan-v2.md` for the revised (monolith-first, scope-reduced) roadmap.

---

## ⛔ Decisions you (the user) must make before implementation starts

These cannot be made autonomously per the project's own operating rules.

| # | Question | Default if you don't decide | Blocks |
|---|---|---|---|
| **U1** | **GPL boundary**: (a) license everything GPL-3.0, (b) get a formal legal opinion, or (c) replace en-croissant entirely | **NONE — blocks impl** | All implementation |
| **U2** | Adopt the revised monolith-first + scope-reduced Phase 1 plan (`phase-plan-v2.md`)? | yes (recommended) | Phase 1 start |
| **U8** | Phase 1 engine roster: Stockfish only (recommended), +Leela, or original 6-engine plan | Stockfish only | Phase 1 start |

These can wait until their respective phases:

| # | Question | Default | Blocks |
|---|---|---|---|
| U3 | Default embedding provider: `nomic-embed-text` local vs `text-embedding-3-small` cloud | nomic-embed-text | Phase 3 |
| U4 | Backend service license (downstream of U1) | Apache-2.0 if U1 permits split | LICENSING.md |
| U5 | Telemetry posture: opt-in / never / opt-in-by-default | never | Phase 8 |
| U6 | Phase-6 FEN-accuracy gate (recommended: ≥97% piece, ≥90% board) | adopt review's numbers | Phase 6 |
| U7 | UI label for the Profile Agent: keep "Psychological Profiling" vs rebrand to "Playing Style Patterns" | rebrand in UI, keep module name internal | Phase 4 |
| U9 | Sidecar packaging: PyInstaller, Docker-launcher shim, or both | PyInstaller | Phase 8 |

---

## Repository Layout (current)

```
chess_coach/
├── README.md                       # this file
├── docs/
│   ├── 01_architecture/            # System architecture (master)
│   ├── 02_modules/                 # 14-module decomposition (+ post-review addenda)
│   ├── 03_technology/              # Technology comparison
│   ├── 04_database/                # Database decision (+ chunking, LRU addenda)
│   ├── 05_desktop_shell/           # Tauri decision
│   ├── 06_multi_agent/             # Bus + tier rules (+ Redis logical-DB addendum)
│   ├── 07_risk/                    # Risk register (now 31 risks, post-review)
│   ├── 08_security/                # Security strategy (+ PDF sandbox, PGN sanitization)
│   ├── 09_performance/             # Performance budgets
│   ├── 10_roadmap/
│   │   ├── phase-plan-v2.md        # ★ ACTIVE roadmap (monolith-first, scope-reduced)
│   │   └── implementation-roadmap-v1.md  # superseded; kept for history
│   ├── 11_repo_structure/          # Repo layout + license posture (TBD pending U1)
│   ├── 12_claude_review/           # The package we sent to Claude for review
│   ├── 13_review_response/         # ★ Review received + our point-by-point response
│   │   ├── claude-review-received.md
│   │   └── response-to-review.md
│   └── research/                   # Raw research (en-croissant, ChessStalker)
└── .a0proj/                        # Agent Zero project metadata (do not modify)
```

---

## Phase 1 Deliverables — Final Status

| # | Deliverable | Status |
|---|---|---|
| 1 | System architecture | ✅ + post-review addenda |
| 2 | Module decomposition | ✅ + 4 post-review addenda |
| 3 | Technology comparison | ✅ + `instructor` adoption |
| 4 | Database decision | ✅ + chunking + LRU |
| 5 | Desktop shell decision | ✅ (unchanged) |
| 6 | Multi-agent workflow | ✅ + DLQ hard requirement + Redis logical-DB split |
| 7 | Risk analysis | ✅ (now 31 risks; 2 eliminated by monolith-first) |
| 8 | Security strategy | ✅ + PDF sandbox + PGN sanitization + same-user secrets caveat |
| 9 | Performance strategy | ✅ (unchanged) |
| 10 | Implementation roadmap | ✅ **superseded by phase-plan-v2.md** |
| 11 | Repo structure | ✅ license cells marked TBD pending U1 |
| 12 | Claude review package | ✅ |
| 13 | **Review response (new)** | ✅ point-by-point accept/modify/reject |

---

## Key changes since the external review

1. **Monolith-first deployment.** 14 conceptual modules still exist but ship inside one Python service for Phase 1–3. Process extraction is empirically driven, not planned upfront.
2. **Phase 1 scope reduced** to: en-croissant fork + Stockfish-only + SQLite + grounded LLM commentary + opening explorer. No Redis, no Qdrant, no Celery, no PDF ingest, no profiling, no saga framework.
3. **GPL boundary is now a user-decision blocker.** Was: asserted. Now: paused until U1 resolves.
4. **Grounded LLM narration pipeline** is now mandatory and architecturally enforced. Free-form LLM coaching output that bypasses it is forbidden by lint rule.
5. **Psychological profiling rigor**: hypothesis + effect-size (Cohen's d ≥ 0.5 to surface) + permanent "experimental" label + non-clinical disclaimer + UI rename (pending U7).
6. **PDF/Vision phase extended** from 3 weeks to 8–12 weeks; dataset-first; PDF parsing in isolated subprocess.
7. **Engine memory tiers** (Lite / Standard / Full) selected at install time; orchestrator enforces budget.
8. **Engine cache key** includes `cpu_arch` and `thread_count`; time-limited search not cached.
9. **DLQ pattern** promoted to hard requirement; bus refuses to start consumers without it.
10. **PGN comment sanitization** required before any PGN-sourced text enters an LLM prompt.

---

## Operating Rules (binding for implementation)

- **NEVER** use destructive inline editors on `.py` / `.tsx` / critical configs.
- ALWAYS commit before major operations.
- ALWAYS `docker commit agentZero agent-zero-with-port9000` before risky Docker ops.
- Backend services run **detached** (`docker exec -d`), never blocking foreground.
- Modular > monolithic for design; **monolithic > microservices for first deployment**.
- Decisions on license / scope / data deletion / publishing / repo identity require explicit user approval.
