# Phase 1 Kickoff — Record

**Date**: 2026-05-18
**Authorized by**: project owner (instruction: "start phase 1 implementation")
**Plan**: `docs/10_roadmap/phase-plan-v2.md`

## Assumed user decisions (applied per project owner's go-ahead)

The user authorized Phase 1 implementation without separately answering U2/U8/U10. The defaults recommended in the README's "Decisions you (the user) must make to close Gate 0" table were applied. If any of these is wrong, the user can correct in their next message and the corresponding work will be revised before further code is written.

| # | Decision | Applied value | If wrong, revise |
|---|---|---|---|
| U2 | Adopt monolith-first + scope-reduced Phase 1 plan? | **yes** | revise `phase-plan-v2.md` and re-plan |
| U8 | Phase 1 engine roster | **Stockfish only** | revise §2.1 of `module-decomposition.md` engine_orch + scope of Phase 1 |
| U10 | CLA template | **Apache ICLA + CCLA, adapted** | revise `CLA-ICLA.md` and `CLA-CCLA.md` |

Deferred user decisions (U3, U4, U5, U6, U7, U9, U11, U12) remain deferred to their phases.

## What was done at kickoff (this commit batch)

### Repository scaffolding

Monorepo top-level layout created per `docs/11_repo_structure/repository-structure.md`:

```
apps/{desktop,cli}/
services/
libs/
infra/{docker,installer/windows,memurai}/
tools/
scripts/
tests/{unit,integration,e2e,perf,golden}/
specs/v1.0/{schemas,tests}/
docs/{14_adrs,15_integration_surfaces}/    # new doc-tree branches
data/{games,books,engines,models,skills,reports,debug,sqlite,secrets}/
```

All workspace directories have placeholder READMEs explaining purpose, license, and Phase-1 planned contents. Empty directories carry `.gitkeep` files so the structure survives in git.

### Governance files (binding)

| File | Purpose | Lines |
|---|---|---|
| `LICENSING.md` | Per-workspace license posture; GPL-3.0 §6 compliance summary; counsel-cleared boundary explanation | 73 |
| `CONTRIBUTING.md` | Contribution guide; CLA gate; coding style; binding "must NOT submit" list | 87 |
| `BUILDING.md` | Reproducible build instructions satisfying GPL-3.0 §6 Installation Information | 128 |
| `CLA-ICLA.md` | Individual CLA, adapted from Apache ICLA v2.2 with broadened sublicensing per P1 | 73 |
| `CLA-CCLA.md` | Corporate CLA, adapted from Apache CCLA v2.0 with same broadened sublicensing | 89 |
| `.gitignore` | Standard ignores for Python / Node / Rust / OS; data/secrets/runtime exclusions | 74 |

Note: CLAs are templates. Final binding versions require legal review with placeholder fills (entity name, governing-law jurisdiction). This is recorded on the file itself.

### Architecture Decision Records (4 new ADRs)

| ADR | Subject | Lines |
|---|---|---|
| 0000 | Template | 38 |
| 0001 | Async/sync boundary in backend services | 62 |
| 0002 | Error envelope and error-code allocation | 52 |
| 0003 | Schema evolution (SQLite migrations + Pydantic versioning) | 50 |
| 0004 | License posture per workspace (records U1 resolution) | 63 |

### Protocol publication

Protocol spec moved from its planning location (`docs/16_protocol/`) to its publication path (`specs/v1.0/chess-coach-protocol-v1.md`). All references in LICENSING.md, ADR-0004, BUILDING.md, CONTRIBUTING.md, and the integration contract already point to the new path. `docs/16_protocol/README.md` left as a forwarding stub.

specs/ tree set up with READMEs explaining license posture (CC-BY-4.0 for spec; MIT for tests) and authoring policy (schemas auto-generated from Pydantic; hand-edits forbidden).

### En-croissant integration-surface contract

`docs/15_integration_surfaces/en-croissant.md` (183 lines) — the binding engineering contract that protects the GPL-3.0 §5 separate-works position **in code**. Defines exactly what we will and will not edit in the upstream fork, the additive-only "coach surface," rebase workflow, and the CI checks that enforce all of this.

## What was NOT done at kickoff

Deferred to the next implementation step (a separate commit batch):

- Fork of en-croissant from a pinned upstream commit into `apps/desktop/`.
- Authoring of `pyproject.toml` and `chess_coach` Python package skeleton.
- Authoring of any `.py` or `.tsx` source files (per binding operating rule, these require careful workflows — heredoc / patch-based — and warrant their own focused commits).
- Setting up CI (`.github/workflows/`) for the enforcement checks called out in the integration contract and ADRs.
- Wiring the CLA bot.
- Populating `specs/v1.0/CHANGELOG.md` and `specs/v1.0/CODES.md`.

## Verification at kickoff

All documents pass:

- Internal cross-references checked manually against current filesystem state.
- All paths referenced in newly-authored documents exist (or are explicitly marked "to be authored at Phase N").
- License posture in `LICENSING.md`, `ADR-0004`, and per-workspace READMEs is consistent.
- Protocol path references updated to `specs/v1.0/` after the move.

## Next implementation step (recommended order)

1. Fork en-croissant into `apps/desktop/` from a pinned commit; author `UPSTREAM.md` and `.upstream-ref`.
2. Author the Python project skeleton (`pyproject.toml`, `chess_coach/__init__.py`, package layout per `services/README.md` + `libs/README.md`).
3. Author `chess_coach.errors` (per ADR-0002) and `chess_coach.storage` migration runner (per ADR-0003) — the two cross-cutting libs.
4. Author `chess_coach.gateway` skeleton: FastAPI app, `/v1/system/info`, `/v1/system/health`, the error envelope, the bearer-token auth, the backend.json writer.
5. Author `chess_coach.uci` async UCI client + `chess_coach.engine_orch` Stockfish adapter.
6. Build the first vertical slice: open a PGN, run Stockfish, get analysis back, render in a stub coach panel.
7. Add grounded narration on top of the vertical slice.

Each is its own focused commit batch.

## Standing reminder

Three binding architectural commitments are now in force and must be honored by every commit:

1. **P1** — Every external Backend PR requires a signed CLA before merge.
2. **P2** — The GUI binary must run identically whether signed or self-built; the auto-updater must be disablable.
3. **P3** — The public protocol is the only communication channel between GUI and Backend; the Pydantic models that generate it are the single source of truth.

Additionally:

- **Grounded-narration pipeline mandatory** for all user-facing LLM output.
- **Tier rules** (`docs/06_multi_agent/multi-agent-workflow.md`) enforced by CI.
- **No new external service dependency** without an ADR.
