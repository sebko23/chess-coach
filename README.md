# CHESS COACH

**Grandmaster-level autonomous chess coaching platform.**

## Project Status

**Phase 1 — Architecture Analysis: ✅ COMPLETE.**
**External (Claude.ai) review: ✅ RECEIVED AND INTEGRATED.**
**OSS legal counsel review: ✅ COMPLETE — U1 (GPL boundary) RESOLVED 2026-05-18.**
**Protocol contract v1.0.0: ✅ PUBLISHED (R1 + R2 applied per counsel).**
**Gate 0: 🟡 OPEN — closes when user confirms U2, U8, U10 (no further external dependencies).**
**Implementation: ⏳ Begins immediately after Gate 0 closes.**

---

## Counsel's final verdict (verbatim)

> Plausibly no, with **low** residual risk, conditional on one targeted revision (R1) to §2 of the protocol spec.
>
> **Conclusion for the project record**: With R1 applied, this protocol contract supports the conclusion that the GUI and Backend are separate works in an aggregate under GPL-3.0 §5. The "intimacy of communication" residual uncertainty identified in the prior analysis is resolved in your favour by the protocol's design. **U1 (GPL boundary decision) may be treated as resolved — not merely conditionally — subject to P1+P2+P3 adoption as binding requirements and R1 being applied before v1.0.0 is published.**

R1 and R2 have been applied; v1.0.0 is cut and published. Full assessment is preserved in `docs/13_review_response/legal-protocol-assessment-received.md`.

---

## Decisions you (the user) must make to close Gate 0

These are the only remaining items between us and writing code. All three are user-only decisions; no further legal or external review is needed.

| # | Question | Recommendation |
|---|---|---|
| **U2** | Adopt the monolith-first + scope-reduced Phase 1 plan (`phase-plan-v2.md`)? | yes |
| **U8** | Phase 1 engine roster: Stockfish only / +Leela / original 6 | Stockfish only |
| **U10** | CLA template: Apache ICLA+CCLA vs alternative | Apache ICLA+CCLA |

### Non-blocking decisions (deferred to their phases)

| # | Question | Default | Phase |
|---|---|---|---|
| U3 | Default embedding provider: nomic-embed-text local vs OpenAI cloud | nomic-embed-text | 3 |
| U4 | Backend service license (now unblocked, recommended Apache-2.0) | Apache-2.0 | gate-1 |
| U5 | Telemetry posture: opt-in / never / opt-in-by-default | never | 8 |
| U6 | Phase-6 FEN-accuracy gate | ≥97% piece, ≥90% board | 6 |
| U7 | UI label for Profile Agent | rebrand UI to "Playing Style Patterns"; keep module name | 4 |
| U9 | Sidecar packaging: PyInstaller / Docker-launcher / both | PyInstaller | 8 |
| U11 | CLA gating tooling | cla-assistant.io | gate-1 |
| U12 | Protocol spec license | CC-BY-4.0 (already set in v1.0.0) | resolved |

---

## Architectural commitments now binding

| Commitment | Source | Where it lives |
|---|---|---|
| **P1 — CLA with broad sublicensing grant** | counsel priority | `docs/13_review_response/legal-opinion-integration.md` §C.1 |
| **P2 — Non-blocking auto-updater (GPL-3.0 §6 Installation Information)** | counsel priority | `docs/08_security/security-strategy.md` post-legal addendum + `legal-opinion-integration.md` §C.2/§H |
| **P3 — Public protocol spec, third-party-implementable** | counsel priority | `docs/16_protocol/chess-coach-protocol-v1.md` v1.0.0 |
| **R1 — §2.1 Standard Bearer Credential language** | counsel mandatory revision | `docs/16_protocol/chess-coach-protocol-v1.md` §2.1 |
| **R2 — §5.1 Diagnostic-only log topic language** | counsel recommended revision | `docs/16_protocol/chess-coach-protocol-v1.md` §5.1 |
| Monolith-first deployment (Phase 1–3) | Claude.ai review | `docs/10_roadmap/phase-plan-v2.md` |
| Scope-reduced Phase 1 (Stockfish + SQLite + grounded narration) | Claude.ai review | `phase-plan-v2.md` |
| Grounded LLM narration pipeline (mandatory) | Claude.ai review | `docs/02_modules/module-decomposition.md` § A-F6 + protocol §8 |
| Engine memory tiers (Lite / Standard / Full) | Claude.ai review | module-decomposition § A-F2 |
| Engine cache key includes `cpu_arch` + `thread_count` | Claude.ai review | module-decomposition § 3 |
| DLQ pattern as bus pre-start requirement | Claude.ai review | multi-agent § Failure handling |
| PGN comment sanitization before any LLM ingestion | Claude.ai review | security-strategy § A-F12 |
| PDF parsing in isolated subprocess | Claude.ai review | security-strategy § A-F11 |
| Diagram-boundary-aware chunking | Claude.ai review | database-decision § A-F8 |
| Engine cache size cap + LRU at `(fen, engine_id)` prefix | Claude.ai review | database-decision § A-F9 |

---

## Repository Layout (current)

```
chess_coach/
├── README.md                       # this file
├── docs/
│   ├── 01_architecture/system-architecture.md
│   ├── 02_modules/module-decomposition.md
│   ├── 03_technology/technology-comparison.md
│   ├── 04_database/database-decision.md
│   ├── 05_desktop_shell/desktop-shell-decision.md
│   ├── 06_multi_agent/multi-agent-workflow.md
│   ├── 07_risk/risk-analysis.md
│   ├── 08_security/security-strategy.md
│   ├── 09_performance/performance-strategy.md
│   ├── 10_roadmap/
│   │   ├── phase-plan-v2.md                       # ★ ACTIVE roadmap
│   │   └── implementation-roadmap-v1.md           # superseded
│   ├── 11_repo_structure/repository-structure.md
│   ├── 12_claude_review/claude-review-package.md
│   ├── 13_review_response/
│   │   ├── claude-review-received.md
│   │   ├── response-to-review.md
│   │   ├── legal-questions-brief.md
│   │   ├── legal-opinion-integration.md
│   │   └── legal-protocol-assessment-received.md  # ★ counsel's verdict (verbatim)
│   ├── 16_protocol/
│   │   └── chess-coach-protocol-v1.md             # ★ v1.0.0 STABLE
│   ├── research/
│   │   ├── en-croissant-analysis.md
│   │   ├── chessstalker-concepts.md
│   │   └── en-croissant-LICENSE.txt
│   └── diagrams/
└── .a0proj/
```

---

## What happens when you close Gate 0

On confirmation of U2 + U8 + U10, Phase 1 implementation begins immediately, in this order (per `phase-plan-v2.md`):

1. Fork en-croissant from a pinned tag; commit `apps/desktop/` per `repo-structure`.
2. Author `CONTRIBUTING.md`, `CLA-ICLA.md`, `CLA-CCLA.md` (using selected template), `BUILDING.md`, `LICENSING.md`. Wire CLA gate into CI.
3. Publish `docs/16_protocol/chess-coach-protocol-v1.md` as `specs/v1.0/` in the public repo; commit JSON Schemas under `specs/v1.0/schemas/`.
4. Author en-croissant integration-surface contract under `docs/15_integration_surfaces/`.
5. Begin the vertical slice: SQLite schema + Stockfish 18 integration + FastAPI gateway + grounded narration pipeline + first React panel in `panels/coach/`.

---

## Operating Rules (binding for implementation)

- **NEVER** use destructive inline editors on `.py` / `.tsx` / critical configs.
- ALWAYS commit before major operations.
- ALWAYS `docker commit agentZero agent-zero-with-port9000` before risky Docker ops.
- Backend services run **detached** (`docker exec -d`).
- Modular > monolithic for design; **monolithic > microservices for first deployment**.
- License / scope / data deletion / publishing / repo identity decisions require explicit user approval.
- CLA wired into CI before any external PR is merged to the Backend.
- GPL-3.0 §6 anti-tivoization rules apply to every GUI binary distribution (no binary signature check at launch, updater disablable, user-built binaries must run unmodified).
