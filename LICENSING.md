# CHESS COACH — Licensing

**Authoritative**: this file. If any other file in this repository disagrees, this file wins until updated.

## Summary

CHESS COACH consists of two binary distribution units. They are licensed independently because they are **separate works in an aggregate** under GPL-3.0-only §5 — a position supported by an OSS-counsel legal opinion received 2026-05-18 (preserved in `docs/13_review_response/legal-protocol-assessment-received.md`).

| Workspace | Distribution unit | License | Reason |
|---|---|---|---|
| `apps/desktop/` | `chess-coach-gui.exe` (and equivalent on other OSes) | **GPL-3.0-only** | Fork of [en-croissant](https://github.com/franciscoBSalgueiro/en-croissant) (GPL-3.0-only). License inherited; cannot be relaxed while we keep the fork. |
| `services/`, `libs/`, `apps/cli/` | `chess-coach-backend.exe` (and equivalent), plus all Python libs | **Apache-2.0** | Original work; communicates with the GUI only via the public protocol; not linked to en-croissant. |
| `specs/` | The protocol specification document and JSON Schemas | **CC-BY-4.0** | Documentation-of-interface, not code. Licensed permissively so any third party may publish a conforming implementation. |
| `specs/v1.0/tests/` | Reference test code | **MIT** | Test code is generally useful outside CHESS COACH; permissive license maximizes reuse. |
| `docs/` | All architecture and project documentation | **CC-BY-4.0** | Documentation. |
| `tests/`, `tools/`, `scripts/`, `infra/` | Internal tooling, tests, CI, build configs | **Apache-2.0** | Same posture as services. |

## Why the boundary holds

The GUI (`apps/desktop/`) and the Backend (`services/`, `libs/`, `apps/cli/`) communicate **only** through the protocol defined in `specs/v1.0/chess-coach-protocol-v1.md` (CC-BY-4.0), which is:

- a public, third-party-implementable specification,
- versioned independently of either binary,
- explicitly conforming to the FSF GPL FAQ's "separate programs communicating via sockets" pattern,
- structurally designed to make GUI/Backend independence observable and verifiable.

The two binaries:

- run as **separate OS processes**,
- have **no shared address space**, no FFI, no dynamic linking, no shared object code,
- communicate **only** over loopback HTTP/WS with a standard bearer-token credential that the protocol explicitly designates as not tied to process identity or binary signature,
- can each be replaced by a third-party conforming implementation without modifying the other.

Counsel's project-record conclusion (verbatim):

> With R1 applied, this protocol contract supports the conclusion that the GUI and Backend are separate works in an aggregate under GPL-3.0 §5. The "intimacy of communication" residual uncertainty identified in the prior analysis is resolved in your favour by the protocol's design.

## GPL-3.0 §6 (Installation Information) compliance

The GUI binary, being GPL-3.0-only, carries §6 Installation Information obligations. CHESS COACH honors these per **P2** (binding architectural rule in `docs/08_security/security-strategy.md` post-legal addendum):

- The GUI binary runs with **no signature check on the binary itself** at launch. Signature verification applies only to update manifests.
- The auto-updater is **disablable** and can be pointed at an alternate update server.
- `BUILDING.md` is sufficient for a competent developer to build a runnable GUI from source on commodity hardware with free tools.
- User-built modified GUI binaries run **identically** to our signed builds against any conforming Backend.

## Bundled GPL-licensed engines

Stockfish (and any later GPL-3.0 engines we bundle) are distributed under their own licenses. CHESS COACH satisfies its §6 source-availability obligations for these by:

- Documenting each engine's upstream URL, version, and license in `BUILDING.md` and in the installer notes.
- Linking to the upstream source repository at the exact tag/commit we built from.
- Not modifying engine sources we redistribute (if we ever do modify, we publish the modified sources alongside).

## Trademark and attribution

We retain upstream copyright notices in modified files within `apps/desktop/`. We do not claim endorsement by en-croissant or its author. The CHESS COACH brand is distinct from en-croissant; we credit en-croissant in the "About" dialog and in `apps/desktop/README.md`.

## Changing licenses

Changing the license of any workspace requires:

1. A user (project owner) decision, explicit and recorded in a new ADR.
2. For `services/`/`libs/`/`apps/cli/` (currently Apache-2.0): collection of all contributors' consent, **OR** a CLA in force that grants sublicensing rights (this is why P1 / `CLA-ICLA.md` exists).
3. For `apps/desktop/` (GPL-3.0-only): no change possible while we fork en-croissant — would require either upstream relicensing (unlikely) or a non-GPL GUI replacement.

## Counsel correspondence

- `docs/13_review_response/legal-questions-brief.md` — the 27-question brief sent to counsel
- `docs/13_review_response/legal-opinion-integration.md` — counsel's initial response, integrated
- `docs/13_review_response/legal-protocol-assessment-received.md` — counsel's verdict on the protocol (the one that resolved U1)

Future license questions should be added to a new section of this file and resolved via the same channel.
