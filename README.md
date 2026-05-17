# CHESS COACH

**Grandmaster-level autonomous chess coaching platform.**

## Project Status

**Phase 1 — Architecture Analysis (in progress).**
No implementation code exists yet. This repository currently contains only the
architecture planning package. Implementation begins only after Phase 1 sign-off.

## Repository Layout (current)

```
chess_coach/
├── README.md                  # this file
├── docs/
│   ├── 01_architecture/       # System architecture report
│   ├── 02_modules/            # Module decomposition
│   ├── 03_technology/         # Technology comparisons
│   ├── 04_database/           # Database decision
│   ├── 05_desktop_shell/      # Electron vs Tauri vs alt
│   ├── 06_multi_agent/        # Multi-agent workflow
│   ├── 07_risk/               # Risk analysis
│   ├── 08_security/           # Security strategy
│   ├── 09_performance/        # Performance strategy
│   ├── 10_roadmap/            # Implementation roadmap
│   ├── 11_repo_structure/     # Proposed code repo structure
│   ├── 12_claude_review/      # External (Claude) review package
│   ├── research/              # Raw research notes (en-croissant, chessstalker, engines)
│   └── diagrams/              # ASCII / mermaid diagrams
└── .a0proj/                   # Agent Zero project metadata (do not modify)
```

## Deliverables (Phase 1)

| # | Deliverable                            | Location                              | Status  |
|---|----------------------------------------|---------------------------------------|---------|
| 1 | System architecture report             | docs/01_architecture/                 | pending |
| 2 | Module decomposition report            | docs/02_modules/                      | pending |
| 3 | Technology comparison report           | docs/03_technology/                   | pending |
| 4 | Database decision report               | docs/04_database/                     | pending |
| 5 | Desktop shell recommendation report    | docs/05_desktop_shell/                | pending |
| 6 | Multi-agent workflow report            | docs/06_multi_agent/                  | pending |
| 7 | Risk analysis report                   | docs/07_risk/                         | pending |
| 8 | Security strategy report               | docs/08_security/                     | pending |
| 9 | Performance strategy report            | docs/09_performance/                  | pending |
|10 | Implementation roadmap                 | docs/10_roadmap/                      | pending |
|11 | Recommended repository structure       | docs/11_repo_structure/               | pending |
|12 | Claude review package                  | docs/12_claude_review/                | pending |

## Operating Rules (binding)

- **NEVER** use destructive inline editors on `.py` / `.tsx` / critical configs.
- ALWAYS commit before major operations.
- ALWAYS `docker commit agentZero agent-zero-with-port9000` before risky Docker ops.
- Backend services run **detached** (`docker exec -d`), never blocking foreground.
- Modular > monolithic. Maintainability > speed.

