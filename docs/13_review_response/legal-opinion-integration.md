# Legal Opinion — Integration of Counsel's Three Pre-Coding Priorities

**Date received**: 2026-05-18
**Source**: External OSS-licensing counsel, in response to `legal-questions-brief.md`
**Status**: Counsel addressed all 27 questions; closing observations identified **three highest-priority pre-coding actions** that materially shift CHESS COACH's legal posture if adopted. This document integrates those three actions into the architecture package as binding requirements.

---

## A. Counsel's Three Priorities (verbatim summary)

**P1. CLA with broad sublicensing grant before any external contributor submits a PR to the Backend.**
Counsel: "the single most asymmetric risk — costs almost nothing to implement now and is extremely expensive to retrofit later."

**P2. Design the auto-updater to be non-blocking (users can install self-built binaries).**
Counsel: "the §6 Installation Information obligation is real and applies to every GUI binary distribution. This needs to be in the architecture from the start, not bolted on later."

**P3. Publish the HTTP/WS protocol spec as a separate document before launch.**
Counsel: "the strongest single legal fact you can establish for the aggregate argument, and it costs only documentation effort."

Counsel additionally **offered** a precise assessment of the "intimacy of communication" residual uncertainty in Q1, conditional on receiving the actual protocol contract draft.

---

## B. Implied Q1 Verdict

Counsel did not, in the closing observations shared, restate the Q1 verdict in a single phrase. But the structure of the closing observations — three priorities specifically aimed at **strengthening** the aggregate / separate-works position — implies the verdict on Q1 is approximately:

> "Plausibly **NO** (Backend can be permissively licensed) **conditional on**: (1) avoiding contributor-license footguns via P1, (2) honoring §6 Installation Information via P2, (3) establishing genuine independence via P3 + a published protocol that a third party could implement."

**Project status change**: User decision blocker **U1 is conditionally resolved**, conditional on adoption of P1+P2+P3 as binding architectural requirements (which this document establishes) AND on counsel's follow-up precise assessment of the protocol contract (see §F below).

Until counsel's follow-up assessment lands, P1+P2+P3 are committed but production code does not yet start. After the follow-up assessment confirms the aggregate position holds for the specific protocol contract, **implementation can begin**.

---

## C. Integration into the architecture package

### C.1 P1 — Contributor License Agreement

**New binding requirement.** Before any **external** contributor submits a PR to the Backend, a CLA must be:

1. Drafted with a **broad sublicensing grant** to the project entity (sufficient to allow later relicensing if needed — e.g. Apache → GPL, dual-license commercial offerings, etc.).
2. Wired into CI as a hard merge gate (no CLA signature → PR cannot merge).
3. Documented in `CONTRIBUTING.md`.

**Template choice (recommended, pending user confirmation U10)**: the **Apache Software Foundation Individual CLA** (ICLA) and **Corporate CLA** (CCLA) templates, lightly modified to substitute the project entity. The ASF CLAs grant a copyright license sufficient for the FSF's GPL-relicensing-compatible practice and are the most widely recognized in OSS practice.

**Alternative considered and rejected**: the lighter-weight DCO (Developer Certificate of Origin, used by Linux kernel and Git). The DCO does not grant sublicensing rights — only certifies origin — and counsel's P1 specifically calls for a "broad sublicensing grant". DCO would not satisfy P1.

**Tool**: `cla-bot` or `cla-assistant.io` for automated GitHub PR gating. Either is acceptable; final choice is implementation detail.

**Internal contributors (the user + Agent Zero)**: signature one-time at project start. External contributors: signature on first PR.

**Where this lives in the package**:
- New file at gate-1: `CONTRIBUTING.md` (the contributing guide).
- New file at gate-1: `CLA-ICLA.md` and `CLA-CCLA.md` (the agreements themselves).
- ADR-to-be: `docs/14_adrs/ADR-0002-cla-policy.md`.
- Phase-plan-v2 updated to make CLA bot wiring a Phase-1 exit criterion.

### C.2 P2 — Non-blocking auto-updater

**New binding requirement.** The Tauri auto-updater design must comply with GPL-3.0 §6 "Installation Information" (often called the "anti-tivoization" clause). Specifically: a user receiving a binary build of the GPL GUI must be able to **install a self-built modified version** on the same hardware without artificial restriction.

**Architectural implications**:

1. **No code signing key check on user-built binaries.** The auto-updater verifies signatures for **updates from us**, but the application must run **unsigned user-built binaries** without modification. Concretely: signature verification is performed against `update_manifest.json` (which our public key signs), but the running binary itself is not signature-locked.
2. **No remote attestation / DRM-like binding** between the GPL GUI and the auto-updater service.
3. **Public documentation** of how to build and install a modified GUI from source (a `BUILDING.md` document covering Tauri build flags, the en-croissant build prerequisites, and the steps to replace the installed binary).
4. **No vendor lock-in** on the update channel: the user can disable updates entirely, point the updater at their own update server, or simply replace the installed binary by hand.
5. The auto-updater's signing key is **only used to authenticate updates we publish**, never to restrict user freedom to modify and run.

**Where this lives in the package**:
- `docs/08_security/security-strategy.md` § auto-update — add explicit P2 compliance subsection (this document § H below).
- New file at gate-1: `BUILDING.md` (build-from-source instructions).
- ADR-to-be: `docs/14_adrs/ADR-0003-anti-tivoization-compliance.md`.
- Phase-plan-v2: P2 compliance is a Phase-8 (packaging) exit criterion.

**Note**: P2 applies to the GUI binary, **not** to the Backend (Backend's license is what we are working to keep permissive; even if it ends up GPL-3.0 too, the §6 Installation Information obligation only practically bites for the GUI because it is the binary the user is most likely to want to modify).

### C.3 P3 — Public protocol specification

**New binding requirement.** The HTTP + WebSocket protocol between GUI and Backend must be:

1. **Specified in a separate document** (not embedded only in code).
2. **Published publicly** before launch (recommended: as part of the project repository, under CC-BY-4.0 license — distinct from any code license).
3. **Versioned independently** of either binary (e.g. `protocol-v1.0`, `protocol-v1.1`).
4. **Implementable by a third party** in either direction (third party could write an alternative GUI that talks to our Backend, or an alternative Backend that satisfies our GUI's calls).
5. **Stable**: breaking changes require a major version bump and dual-version support during deprecation.

This is the legally most valuable item: it converts "GUI and Backend are de facto separable" from an implementation detail into an **observable, third-party-verifiable fact**.

**Where this lives in the package**:
- New file (drafted in §F below, then iterated): `docs/16_protocol/chess-coach-protocol-v1.md`.
- The protocol document carries its own version, changelog, license declaration (CC-BY-4.0), and reference test vectors.
- ADR-to-be: `docs/14_adrs/ADR-0004-public-protocol-policy.md`.
- Phase-plan-v2: protocol-v1.0 publication is a Phase-1 exit criterion (gate from Phase 1 to Phase 2).

---

## D. New / modified user decisions

| # | Decision | Default | Status |
|---|---|---|---|
| **U1** | GPL boundary | **CONDITIONALLY RESOLVED** — counsel's plausibly-NO verdict, contingent on P1+P2+P3 adoption and follow-up protocol assessment | requires user to confirm acceptance of P1+P2+P3 as binding |
| **U10 (new)** | CLA template — ASF ICLA/CCLA vs. alternative | ASF ICLA + CCLA | requires user sign-off when CLA is drafted |
| **U11 (new)** | CLA gating tooling — `cla-bot` vs `cla-assistant.io` | `cla-assistant.io` (no infra to host) | non-blocking, can be decided at gate-1 |
| **U12 (new)** | Protocol spec license | CC-BY-4.0 | non-blocking |

The other open decisions (U2, U3, U5–U9) are unchanged.

---

## E. Updated phase plan changes

`docs/10_roadmap/phase-plan-v2.md` should be amended so that:

1. **Gate 0** (pre-implementation) now requires user confirmation that P1+P2+P3 are accepted as binding.
2. **Phase 1** exit criteria add:
   - `CONTRIBUTING.md` + ICLA/CCLA + CLA-bot wired into CI.
   - `chess-coach-protocol-v1.md` published in the public repo with version v1.0.
   - `BUILDING.md` published with reproducible build instructions for the GUI.
3. **Phase 8** (packaging) exit criteria add:
   - Auto-updater verified non-blocking against P2 checklist (user can build, install, and run a modified GUI binary without circumventing any signature check).
   - User-visible documentation of the update opt-out and self-hosting paths.

These amendments are appended to `phase-plan-v2.md` as a post-counsel addendum (see also §G below).

---

## F. Next step with counsel: protocol contract draft

Counsel offered a precise assessment of the "intimacy of communication" residual uncertainty if we share the actual protocol contract. We will take that offer.

Action: draft `docs/16_protocol/chess-coach-protocol-v1.md` as a real, technically complete (not stubbed) specification of the v1 GUI↔Backend protocol. Once drafted, send it back to counsel with the following short cover note:

> Per your closing observation #3 and your offer to do a precise §6 assessment, attached is the protocol contract for CHESS COACH v1. Please assess (a) whether the protocol design supports the aggregate / separate-works position you previously characterized as "plausibly NO" on Q1, (b) any specific clauses, endpoints, or design choices that **weaken** the position and that we should revise before publishing, and (c) whether anything in the protocol triggers obligations we have not yet considered (notably §6 of GPL-3.0).

The protocol draft is started in a sibling file (`docs/16_protocol/chess-coach-protocol-v1.md`) — see commit history.

---

## G. Affected docs — change list

| Doc | Change |
|---|---|
| `README.md` | U1 status changes to CONDITIONALLY RESOLVED; surface P1+P2+P3 prominently; surface protocol-spec deliverable as Phase 1 exit criterion |
| `docs/10_roadmap/phase-plan-v2.md` | Append §E amendments (Gate 0 + Phase 1 + Phase 8) |
| `docs/08_security/security-strategy.md` | Append P2 anti-tivoization compliance subsection (§H below) |
| `docs/11_repo_structure/repository-structure.md` | Add `CONTRIBUTING.md`, `CLA-ICLA.md`, `CLA-CCLA.md`, `BUILDING.md` to repo root; add `docs/16_protocol/` |
| `docs/13_review_response/response-to-review.md` | U1 row in table § E updated to CONDITIONALLY RESOLVED |
| **New**: `docs/16_protocol/chess-coach-protocol-v1.md` | The draft protocol contract for counsel's precise assessment |

---

## H. P2 — Auto-updater anti-tivoization compliance (full subsection)

The following subsection is the canonical statement of P2 compliance. It is also appended (in a slightly shorter form) to `08_security/security-strategy.md`.

### H.1 The obligation

GPL-3.0 §6 ("Conveying Non-Source Forms") imposes the **Installation Information** obligation: when conveying a covered work in object code form to a user, the conveyor must provide the user with the information required to install and execute modified versions of the covered work on the same hardware. The colloquial name "anti-tivoization" comes from the TiVo case that motivated this clause.

For CHESS COACH, this obligation applies to **the GUI binary** (`chess-coach-gui.exe`), which is derived from the GPL-3.0 en-croissant fork.

### H.2 Architectural rules (binding)

1. The GUI binary **MUST** run on the user's machine **without any signature check on the binary itself**. Specifically: Tauri's `tauri-updater` plugin signature verification applies to **update manifests** (so we can authenticate updates we publish), **not** to the binary at launch.
2. The auto-updater **MUST** be **disablable** by the user (a Settings UI toggle + a config file flag).
3. The user **MUST** be able to **point the auto-updater at a different update server** (their own, or none).
4. **No code path** in the GUI may refuse to run, downgrade functionality, or display warnings based on whether the running binary was built by us vs. by the user.
5. The build instructions (`BUILDING.md`) **MUST** be sufficient for a competent developer to build a runnable GUI binary from the published source, on commodity hardware, using only free tools.
6. Any **bundled engine binaries** (Stockfish) we ship under §6 must independently honor their own GPL-3.0 source-availability obligations — this is satisfied by linking to upstream repositories in our distribution documentation.

### H.3 What is allowed

- Signed update manifests authenticating updates **we** publish.
- Refusing to apply an update whose manifest signature does not validate against our public key (this is about update integrity, not user freedom).
- Telemetry collection that is **opt-in** (per U5) and that does not affect runtime behavior.
- Optional integrity checks the user can disable.

### H.4 What is forbidden

- Refusing to launch a user-built binary.
- Locking the auto-updater to our server only.
- Any "hardware-bound" or "machine-bound" license check that prevents a self-built binary from running.
- DRM-style attestation between the GUI and any external service (including our Backend) that would prevent a user-built GUI from connecting.
- Telemetry that is mandatory for runtime function.
