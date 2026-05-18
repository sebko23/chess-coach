# CHESS COACH

**Grandmaster-level autonomous chess coaching platform.**

## Project Status

**Phase 1 — Architecture Analysis: ✅ COMPLETE.**
**External (Claude.ai) review: ✅ RECEIVED AND INTEGRATED (2026-05-18).**
**OSS legal counsel review: ✅ ALL 27 QUESTIONS ADDRESSED (2026-05-18).**
**U1 (GPL boundary): ⚠️ CONDITIONALLY RESOLVED — pending counsel's protocol-spec follow-up review.**
**Implementation start: ⛔ NOT YET — Gate 0 closes when the protocol-review round returns clean.**

---

## Where we are right now

Counsel's verdict on the combined-work question (Q1) is **plausibly NO** — the Backend can be permissively licensed — **conditional on**:

- **P1**: A Contributor License Agreement with a broad sublicensing grant, wired into CI as a hard merge gate, before any external contributor touches the Backend.
- **P2**: A **non-blocking auto-updater** that honors GPL-3.0 §6 "Installation Information" — users must be able to install self-built modified GUI binaries on the same hardware.
- **P3**: The HTTP/WS protocol between GUI and Backend published as a **separate public specification** before launch (the strongest single fact establishing the aggregate position).

These three are now **binding architectural requirements**, integrated into the package (see §"Key changes since legal review" below).

Counsel additionally **offered** a precise §6 assessment of the protocol contract once we draft it. **We have done that.** The draft is at `docs/16_protocol/chess-coach-protocol-v1.md` (543 lines, CC-BY-4.0, includes Appendix A explaining design intent for legal review).

**Immediate next step for the user**: send the protocol draft back to counsel for the precise §6 assessment, with this cover note (also embedded in `docs/13_review_response/legal-opinion-integration.md` § F):

> Per your closing observation #3 and your offer to do a precise §6 assessment, attached is the protocol contract for CHESS COACH v1. Please assess (a) whether the protocol design supports the aggregate/separate-works position you previously characterized as "plausibly NO" on Q1, (b) any specific clauses, endpoints, or design choices that **weaken** the position and that we should revise before publishing, and (c) whether anything in the protocol triggers obligations we have not yet considered (notably §6 of GPL-3.0).

---

## Decisions you (the user) must make

### Blocking Gate 0

| # | Question | Default | Status |
|---|---|---|---|
| U1 | GPL boundary | **CONDITIONALLY RESOLVED** pending protocol-review | adopt P1+P2+P3 binding requirements? |
| U2 | Adopt monolith-first + scope-reduced Phase 1 plan? | yes (recommended) | open |
| U8 | Phase 1 engine roster: Stockfish only / +Leela / original 6 | Stockfish only | open |
| **U10 (new)** | CLA template: Apache ICLA+CCLA vs alternative | Apache ICLA+CCLA | open |

### Non-blocking (can wait until their phases)

| # | Question | Default | Phase |
|---|---|---|---|
| U3 | Default embedding provider: nomic-embed-text local vs OpenAI cloud | nomic-embed-text | 3 |
| U4 | Backend service license (downstream of U1 final) | Apache-2.0 if U1 permits | gate-1 |
| U5 | Telemetry posture: opt-in / never / opt-in-by-default | never | 8 |
| U6 | Phase-6 FEN-accuracy gate | ≥97% piece, ≥90% board | 6 |
| U7 | UI label for Profile Agent: "Psychological Profiling" vs "Playing Style Patterns" | rebrand UI to "Playing Style Patterns" | 4 |
| U9 | Sidecar packaging: PyInstaller / Docker-launcher / both | PyInstaller | 8 |
| **U11 (new)** | CLA gating tooling: cla-bot vs cla-assistant.io | cla-assistant.io | gate-1 |
| **U12 (new)** | Protocol spec license | CC-BY-4.0 | gate-1 |

---

## Key changes since legal review

1. **U1 conditionally resolved** by external counsel's plausibly-NO verdict, contingent on P1+P2+P3 (above).
2. **P1 (CLA)**: Apache ICLA+CCLA recommended; binding before any external PR to the Backend. Documented in `docs/13_review_response/legal-opinion-integration.md` §C.1.
3. **P2 (anti-tivoization)**: Auto-updater architecture now has binding rules (no binary signature check at launch; updater disablable; user-built binaries must run identically). Documented in `docs/08_security/security-strategy.md` post-legal addendum and in `docs/13_review_response/legal-opinion-integration.md` §C.2 + §H.
4. **P3 (public protocol)**: Draft at `docs/16_protocol/chess-coach-protocol-v1.md` (CC-BY-4.0, 543 lines, normative §1–§13, conformance §12, schema index §15, appendix for counsel §A). Awaiting counsel's precise §6 review.
5. **Phase-plan-v2 amended**: Gate 0 and Phase 1 and Phase 8 exit criteria updated to enforce P1/P2/P3.
6. **Repo structure amended**: `CONTRIBUTING.md`, `CLA-ICLA.md`, `CLA-CCLA.md`, `BUILDING.md`, `LICENSING.md` added at root; `docs/14_adrs/`, `docs/15_integration_surfaces/`, `docs/16_protocol/` added; `specs/v1.0/{schemas,tests}/` added (CC-BY-4.0 for specs; MIT for reference tests).

(Earlier Claude.ai review changes — monolith-first deployment, scope-reduced Phase 1, grounded LLM narration, engine memory tiers, etc. — remain in force; see `docs/13_review_response/response-to-review.md`.)

---

## Repository Layout (current)

```
chess_coach/
├── README.md                       # this file
├── docs/
│   ├── 01_architecture/            # System architecture (master, with addenda)
│   ├── 02_modules/                 # 14-module decomposition (with post-review addenda)
│   ├── 03_technology/              # Technology comparison
│   ├── 04_database/                # Database decision (with chunking + LRU addenda)
│   ├── 05_desktop_shell/           # Tauri decision
│   ├── 06_multi_agent/             # Bus + tier rules (with Redis-DB-split addendum)
│   ├── 07_risk/                    # 31-risk register
│   ├── 08_security/                # Security strategy (with P2 anti-tivoization addendum)
│   ├── 09_performance/             # Performance budgets
│   ├── 10_roadmap/
│   │   ├── phase-plan-v2.md        # ★ ACTIVE roadmap (with post-legal amendments)
│   │   └── implementation-roadmap-v1.md
│   ├── 11_repo_structure/          # Repo layout (with post-legal addendum)
│   ├── 12_claude_review/           # Package we sent to Claude.ai for review
│   ├── 13_review_response/         # Review + responses (Claude + Legal)
│   │   ├── claude-review-received.md
│   │   ├── response-to-review.md
│   │   ├── legal-questions-brief.md
│   │   └── legal-opinion-integration.md     ★ counsel's three priorities, integrated
│   ├── 16_protocol/                # ★ NEW: public protocol contract
│   │   └── chess-coach-protocol-v1.md       ★ draft, send to counsel for §6 review
│   ├── research/                   # en-croissant + ChessStalker + GPL LICENSE
│   └── diagrams/
└── .a0proj/
```

---

## Phase 1 Deliverables — Final Status

| # | Deliverable | Status |
|---|---|---|
| 1 | System architecture | ✅ + post-review addenda |
| 2 | Module decomposition | ✅ + 4 post-review addenda |
| 3 | Technology comparison | ✅ + `instructor` adoption |
| 4 | Database decision | ✅ + chunking + LRU |
| 5 | Desktop shell decision | ✅ |
| 6 | Multi-agent workflow | ✅ + DLQ + Redis-DB-split |
| 7 | Risk analysis | ✅ 31 risks; 2 eliminated |
| 8 | Security strategy | ✅ + PDF sandbox + PGN sanitization + P2 anti-tivoization |
| 9 | Performance strategy | ✅ |
| 10 | Implementation roadmap | ✅ phase-plan-v2 with legal amendments |
| 11 | Repo structure | ✅ + CLA/BUILDING/protocol additions |
| 12 | Claude review package | ✅ |
| 13 | Review response (Claude.ai) | ✅ |
| 14 | Legal questions brief | ✅ 27 questions sent |
| 15 | Legal opinion integration | ✅ P1/P2/P3 binding |
| 16 | Public protocol contract | ✅ draft v1.0.0-draft.1; awaiting counsel review |

---

## Operating Rules (binding for implementation)

- **NEVER** use destructive inline editors on `.py` / `.tsx` / critical configs.
- ALWAYS commit before major operations.
- ALWAYS `docker commit agentZero agent-zero-with-port9000` before risky Docker ops.
- Backend services run **detached** (`docker exec -d`).
- Modular > monolithic for design; **monolithic > microservices for first deployment**.
- License / scope / data deletion / publishing / repo identity decisions require explicit user approval.
- **New**: CLA must be wired in CI before any external PR is merged to the Backend.
- **New**: GPL-3.0 §6 anti-tivoization rules apply to every GUI binary distribution (no binary signature check, updater disablable, user-built binaries must run unmodified).
