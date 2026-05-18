# Recommended Repository Structure

We will use a **monorepo** with clearly separated workspaces. Rationale: a small team / autonomous-agent project benefits from atomic cross-cutting commits and a single source of truth; the workspaces still enforce module boundaries.

## Top-level layout

```
chess_coach/
├── README.md
├── LICENSING.md                    # explicit license posture for each workspace
├── CHANGELOG.md
├── .a0proj/                         # Agent Zero project metadata (DO NOT MOVE)
├── .gitignore
├── .gitattributes
├── .editorconfig
├── .pre-commit-config.yaml
├── .github/
│   └── workflows/                   # CI: lint, test, build, perf, security
├── docs/                            # Phase-1 architecture package (this dir)
├── tools/                           # Repo-level dev tooling
│   ├── lint_tier_rules.py           # enforces multi-agent tier dep rules
│   ├── gen_claude_bundle.py         # builds the external review package
│   └── data_export_cli.py           # user data export/import
├── infra/
│   ├── docker/
│   │   ├── compose.dev.yml          # dev environment
│   │   ├── compose.test.yml
│   │   ├── compose.prod.yml         # end-user side (used by installer)
│   │   ├── gateway.Dockerfile
│   │   ├── worker-heavy.Dockerfile
│   │   ├── worker-light.Dockerfile
│   │   └── qdrant.Dockerfile        # pinned Qdrant image
│   ├── installer/
│   │   ├── windows/                 # MSI + NSIS scripts
│   │   ├── pyinstaller.spec         # sidecar binary build spec
│   │   └── README.md
│   └── memurai/                     # Redis-on-Windows redistribution
│
├── apps/
│   ├── desktop/                     # Tauri shell (Rust + en-croissant fork)
│   │   ├── src-tauri/
│   │   │   ├── src/
│   │   │   ├── tauri.conf.json
│   │   │   └── Cargo.toml
│   │   ├── src/                     # React app (en-croissant base)
│   │   │   ├── components/          # upstream components — touch sparingly
│   │   │   ├── panels/
│   │   │   │   ├── coach/           # ★ CHESS COACH new panels live HERE
│   │   │   │   │   ├── ProfilePanel.tsx
│   │   │   │   │   ├── TrainingDashboard.tsx
│   │   │   │   │   ├── HeatmapView.tsx
│   │   │   │   │   ├── RepertoireExplorer.tsx
│   │   │   │   │   ├── AgentMonitor.tsx
│   │   │   │   │   ├── DebugPanel.tsx
│   │   │   │   │   └── …
│   │   │   │   └── upstream/        # upstream panels (analysis board, etc.)
│   │   │   ├── lib/
│   │   │   │   ├── api/             # generated TS client from FastAPI OpenAPI
│   │   │   │   ├── ws/              # WS subscription helpers
│   │   │   │   └── state/           # Zustand stores
│   │   │   └── pages/
│   │   ├── public/
│   │   ├── package.json
│   │   └── README.md                # documents which en-croissant tag we forked from
│   └── cli/                         # `chess-coach` CLI
│       └── pyproject.toml
│
├── services/                        # Python backend (one workspace per agent service)
│   ├── gateway/                     # FastAPI gateway: auth, routing, WS fanout
│   │   ├── pyproject.toml
│   │   ├── src/chess_coach_gateway/
│   │   └── tests/
│   ├── engine_orchestrator/
│   ├── analysis_agent/
│   ├── profile_agent/
│   ├── kb_agent/
│   ├── pdf_vision_agent/
│   ├── training_planner/
│   ├── repertoire_agent/
│   ├── research_agent/
│   ├── memory_agent/
│   ├── reporting_agent/
│   ├── debug_agent/
│   └── sync_agent/
│
├── libs/                            # Shared Python libraries (consumed by services)
│   ├── chess_coach_core/            # domain types: FEN, Move, Game, Position
│   │   ├── pyproject.toml
│   │   └── src/chess_coach/core/
│   ├── chess_coach_bus/             # Redis Streams envelope + helpers
│   ├── chess_coach_db/              # SQLite + Qdrant access layer + migrations
│   │   ├── alembic/
│   │   └── src/chess_coach/db/
│   ├── chess_coach_llm/             # LLM Router library (Tier 2)
│   │   ├── src/chess_coach/llm/
│   │   └── prompts/                 # markdown prompt templates
│   ├── chess_coach_engines/         # UCI engine pool + adapters
│   └── chess_coach_telemetry/       # structlog setup + OTel + redaction filter
│
├── data/                            # ★ runtime data dir (gitignored; user-owned)
│   ├── games/                       # PGN cache
│   ├── books/                       # uploaded PDFs + extracted artifacts
│   ├── engines/                     # installed engine binaries
│   ├── models/                      # YOLO + piece-classifier weights
│   ├── skills/                      # procedural memory (markdown)
│   ├── reports/
│   ├── debug/                       # diagnostic dumps
│   ├── qdrant/                      # Qdrant on-disk storage
│   ├── sqlite/                      # chess_coach.db + WAL
│   └── secrets/                     # session token only (real secrets in OS keychain)
│
├── tests/
│   ├── unit/                        # per-library unit tests
│   ├── integration/                 # cross-service tests using compose.test.yml
│   ├── e2e/                         # Playwright-driven E2E against the Tauri shell
│   ├── perf/                        # pytest-benchmark + budgets.yaml
│   └── golden/                      # golden-output fixtures (analysis, profiles)
│
└── scripts/                         # one-off / operational scripts
    ├── bootstrap_dev.sh
    ├── seed_demo_data.py
    └── rotate_token.py
```

## License posture per workspace

**⚠️ Post-review status: ALL non-GUI license cells are TBD pending the user decision on the GPL boundary (see `docs/13_review_response/response-to-review.md` U1). Defaults below are the *original* proposal, NOT a decision.**

| Path | License (PROPOSED — pending U1) | Reason |
|---|---|---|
| `apps/desktop/` (the Tauri shell, en-croissant fork) | **GPL-3.0-only** (forced by en-croissant) | Inherited from en-croissant; not negotiable while we keep the fork. |
| `apps/cli/` | TBD by user | Decoupled from GUI. |
| `services/*` | TBD by user (proposed default: Apache-2.0 IF legal opinion permits; otherwise GPL-3.0-only) | Process-separated; treatment depends on combined-work analysis. |
| `libs/*` | Same as services | Imported by services only. |
| `docs/` | CC-BY-4.0 | Documentation. |

`LICENSING.md` will be authored at gate-1 (after U1 resolves), not earlier.

## Why monorepo vs polyrepo

- **Atomic refactors** across gateway + services + frontend types are common (e.g. changing an event schema).
- **Generated artifacts** (TS client from OpenAPI, Pydantic models from JSON schemas) must stay in sync.
- **Single CI pipeline** is simpler for a small team.
- License boundaries are enforced by **directory** + `LICENSING.md`, not by repo separation. Courts care about distribution units, not git topology; our distribution units (Tauri app vs backend binary) remain separate.

We accept the cost of slower CI on touch-all-services changes; we mitigate with path-filtered workflow triggers.

## Git workflow

- **Trunk-based** with short-lived feature branches `feat/<scope>`, `fix/<scope>`, `chore/<scope>`, `docs/<scope>`.
- Conventional Commits enforced by commitlint.
- PRs squash-merged.
- `main` is always green; tags `vX.Y.Z` trigger release pipelines.
- The fork point from en-croissant is tagged `upstream/en-croissant/vA.B.C` and a documented rebase ritual lives in `apps/desktop/README.md`.

## Branch protection

- Required checks: lint, unit, integration-fast, tier-rule linter.
- Required reviews: 1 (Agent Zero self-review counts as 0; user must approve unless solo dev mode is explicitly enabled).
- No force-pushes to `main`.

## Backup strategy

- `data/` is the user's data. Never in git. **Auto-snapshotted** to `data/_snapshots/<ISO-ts>/` before any migration, schema change, or bulk delete (configurable retention).
- Repo history is the code backup; pushed to user-controlled origin (GitHub private repo or self-hosted).
- Release artifacts are SLSA-attested and stored in GH Releases.

## Rollback strategy

- Code: `git revert <sha>` + CI re-run.
- Data: stop services → restore from latest `data/_snapshots/<ts>/` → run any down-migration if schema bumped → restart.
- Engine binaries: each engine version retained; rollback = flip the active-version symlink.
- Models (YOLO/classifier): versioned in `data/models/<name>/<version>/`; active-version symlink.

## Repo-overwrite protection

- `.gitattributes` marks generated files and large binaries so accidental edits surface in PRs.
- A pre-commit hook refuses commits that touch `.a0proj/` or `LICENSING.md` without `--allow-meta-edit`.
- `tools/lint_tier_rules.py` runs on every commit; failing exits non-zero.


---

## Post-Legal-Opinion Addendum (2026-05-18)

External OSS counsel's P1/P2/P3 require the following additions at repo root and under `docs/`:

```
chess_coach/
├── CONTRIBUTING.md              # contributor guide; references CLA
├── CLA-ICLA.md                  # Apache ICLA, lightly adapted (P1)
├── CLA-CCLA.md                  # Apache CCLA, lightly adapted (P1)
├── BUILDING.md                  # reproducible GUI build instructions (P2)
├── LICENSING.md                 # authored at gate-1 (post-U1-final-resolution)
├── docs/
│   ├── 14_adrs/
│   │   ├── ADR-0001-async-sync-boundary.md
│   │   ├── ADR-0002-cla-policy.md
│   │   ├── ADR-0003-anti-tivoization-compliance.md
│   │   └── ADR-0004-public-protocol-policy.md
│   ├── 15_integration_surfaces/
│   │   └── en-croissant.md      # formal interface contract with upstream
│   └── 16_protocol/
│       └── chess-coach-protocol-v1.md    # drafted, awaiting counsel review
└── specs/
    └── v1.0/
        ├── schemas/             # machine-readable JSON Schemas (P3)
        └── tests/               # reference test vectors
```

The `specs/` directory at repo root is **published independently of source-code licenses**: the protocol specification and JSON Schemas are CC-BY-4.0; reference test code is MIT. This independence is part of P3: a third party may publish a conforming implementation under any license they choose, including proprietary, without touching CHESS COACH source code.
