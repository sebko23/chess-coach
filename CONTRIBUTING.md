# Contributing to CHESS COACH

Thanks for considering a contribution. CHESS COACH is built modularly and welcomes external work, but a few rules are non-negotiable.

## Before you write code

1. **Read `LICENSING.md`.** Know which workspace your change touches and what license applies.
2. **Sign a CLA.** Every external contributor signs either:
   - the **Individual CLA** (`CLA-ICLA.md`) — for individuals contributing on their own behalf, or
   - the **Corporate CLA** (`CLA-CCLA.md`) — for contributors acting on behalf of an employer.

   Signature is collected automatically by the CLA bot on your first pull request. **PRs cannot be merged without a valid signature on file.**

   This is binding architectural requirement P1 (see `docs/13_review_response/legal-opinion-integration.md` §C.1). Without it the project cannot guarantee its license posture; without that we cannot accept contributions to the Backend.

3. **Read the architecture docs.** The relevant doc set lives under `docs/`. At minimum, skim:
   - `docs/01_architecture/system-architecture.md`
   - `docs/02_modules/module-decomposition.md` (find the module(s) your change touches)
   - `docs/10_roadmap/phase-plan-v2.md` (find which phase your change belongs to)

## How to propose a change

### Small change (typo, doc clarity, one-file bug fix)

Open a PR directly. Reference the affected doc / file. The CLA bot will guide you through signature on first contact.

### Larger change (new feature, architectural touch)

Open a GitHub Discussion or issue **first**. Outline:

- the problem,
- the proposed change,
- which architecture doc(s) it impacts,
- whether a new ADR is needed (architectural change), see `docs/14_adrs/`.

After discussion alignment, open the PR.

## What to test

Every PR must pass:

- `pytest` for Python code (unit + integration suites the change touches)
- `pnpm test` / `pnpm lint` / `pnpm typecheck` for TypeScript code
- the tier-rule namespace-package check (CI runs it; you don't have to run it locally unless it fails)
- conformance tests when changing anything that touches the protocol (`specs/v1.0/tests/`)

New code without tests is not accepted unless the change is doc-only or pure config.

## Coding style

- **Python**: `ruff` + `black` + `mypy --strict`. CI enforces.
- **TypeScript / TSX**: `biome` (lint + format unified). CI enforces.
- **Rust** (Tauri shell only): `cargo fmt` + `cargo clippy --all -- -D warnings`.

## Commit messages

Conventional Commits format. Examples:

- `feat(engine_orch): add Leela Chess Zero adapter`
- `fix(narration): guard against empty motif list in grounding validator`
- `docs(roadmap): clarify Phase 6 FEN-accuracy gate criterion`
- `chore(deps): bump python-chess to 1.999`

Scope is the affected module or area, lowercased. Use `!` after the type for breaking changes (`feat(protocol)!: …`).

## What you must NOT submit

Per the project's binding operating rules:

- **No license changes** without a prior ADR and user (project owner) approval.
- **No new external service dependencies** without an ADR.
- **No code that bypasses the grounded-narration pipeline** for user-facing LLM output (`docs/02_modules/module-decomposition.md` § A-F6).
- **No code that ties the auto-updater to a specific binary identity, signature, or launch parent** (GPL-3.0 §6 anti-tivoization; see `docs/08_security/security-strategy.md` post-legal addendum).
- **No code that exposes the gateway on a non-loopback interface by default**.
- **No PR that touches `.a0proj/`** without explicit owner approval.

## Reviewer expectations

Reviews are honest and adversarial. Expect questions about architecture fit, tier-rule compliance, test coverage, and whether the change earns its complexity. Friendly tone is required; pushback is normal.

## Maintainers

The project owner (currently the original developer) has final say on architecture and license decisions. Day-to-day code reviews can be done by any maintainer designated in `.github/CODEOWNERS` (to be populated as the project grows).

## Reporting security issues

Do not open public issues for security problems. Email security@chess-coach.local (placeholder; replace with real contact at publication). See `docs/08_security/security-strategy.md` for our security posture.
