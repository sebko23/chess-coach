# CHESS COACH

**Grandmaster-level autonomous chess coaching platform.**

## Project Status

**Phase 1 — Architecture Analysis: ✅ COMPLETE (2026-05-18).**
All 12 architecture deliverables produced. No implementation code yet — by design. Awaiting user / external (Claude) review at gate 0 before Phase 1 implementation begins (see roadmap).

## Repository Layout (current)

```
chess_coach/
├── README.md                  # this file
├── docs/
│   ├── 01_architecture/       # System architecture report (master)
│   ├── 02_modules/            # 14-module decomposition
│   ├── 03_technology/         # Technology comparison
│   ├── 04_database/           # Database decision (SQLite + Qdrant)
│   ├── 05_desktop_shell/      # Desktop shell decision (Tauri)
│   ├── 06_multi_agent/        # Multi-agent workflow + bus + tier rules
│   ├── 07_risk/               # Risk analysis (20 risks)
│   ├── 08_security/           # Security strategy
│   ├── 09_performance/        # Performance strategy + budgets
│   ├── 10_roadmap/            # 9-phase implementation roadmap
│   ├── 11_repo_structure/     # Recommended code repo structure
│   ├── 12_claude_review/      # External (Claude) review package
│   ├── research/              # Raw research (en-croissant, ChessStalker)
│   └── diagrams/              # (reserved; ASCII diagrams inline in docs)
└── .a0proj/                   # Agent Zero project metadata (do not modify)
```

## Deliverables (Phase 1)

| # | Deliverable                            | Location                              | Status |
|---|----------------------------------------|---------------------------------------|--------|
| 1 | System architecture report             | docs/01_architecture/                 | ✅ |
| 2 | Module decomposition report (14 modules) | docs/02_modules/                    | ✅ |
| 3 | Technology comparison report           | docs/03_technology/                   | ✅ |
| 4 | Database decision report               | docs/04_database/                     | ✅ |
| 5 | Desktop shell recommendation report    | docs/05_desktop_shell/                | ✅ |
| 6 | Multi-agent workflow report            | docs/06_multi_agent/                  | ✅ |
| 7 | Risk analysis report                   | docs/07_risk/                         | ✅ |
| 8 | Security strategy report               | docs/08_security/                     | ✅ |
| 9 | Performance strategy report            | docs/09_performance/                  | ✅ |
|10 | Implementation roadmap (9 phases)      | docs/10_roadmap/                      | ✅ |
|11 | Recommended repository structure       | docs/11_repo_structure/               | ✅ |
|12 | Claude review package                  | docs/12_claude_review/                | ✅ |

## Key Phase-1 Decisions (TL;DR)

- **Desktop shell**: Tauri 2.x (preserves en-croissant; better resource posture than Electron).
- **Backend language**: Python 3.11 + FastAPI; multi-process agents.
- **Architecture**: 14 specialized agents with tier-rule dependency graph; Redis Streams bus.
- **Persistence**: SQLite (WAL) + Qdrant (vectors) + filesystem; Postgres upgrade path documented.
- **LLM**: OpenRouter primary via a central `llm_router` library; LLMs used surgically (narration, summarization) not as a main control loop.
- **License posture**: GUI fork is GPL-3.0-only (inherited from en-croissant); backend services run as separate processes and are licensed independently (default: Apache-2.0).
- **Deployment**: Docker for dev, PyInstaller sidecar for end-user installs.

## How to Review

1. Start with **`docs/01_architecture/system-architecture.md`** (master integrative doc).
2. Drill into module specs at **`docs/02_modules/`**.
3. Read the **`docs/12_claude_review/claude-review-package.md`** — it is the token-efficient summary for external review and lists the open questions we most want pressure-tested.

## Operating Rules (binding for implementation)

- **NEVER** use destructive inline editors on `.py` / `.tsx` / critical configs.
- ALWAYS commit before major operations.
- ALWAYS `docker commit agentZero agent-zero-with-port9000` before risky Docker ops.
- Backend services run **detached** (`docker exec -d`), never blocking foreground.
- Modular > monolithic. Maintainability > speed.

