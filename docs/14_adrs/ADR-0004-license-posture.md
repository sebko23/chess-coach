# ADR-0004: License posture per workspace

- **Status**: accepted
- **Date**: 2026-05-18
- **Deciders**: project owner
- **Consulted**: OSS counsel (verdict 2026-05-18, see `docs/13_review_response/legal-protocol-assessment-received.md`)

## Context

U1 (the GPL-3.0 boundary question) was the single biggest open architectural risk. Counsel resolved it: GUI fork (`apps/desktop/`) and Backend (`services/`/`libs/`/`apps/cli/`) constitute **separate works in an aggregate** under GPL-3.0-only §5, with low residual risk, conditional on adoption of P1+P2+P3 as binding and R1+R2 applied to the protocol. All conditions are met.

This ADR records the resulting license-posture decision in immutable form.

## Decision

License per workspace as follows (live state mirrored in `LICENSING.md`):

| Workspace | License |
|---|---|
| `apps/desktop/` | GPL-3.0-only |
| `services/`, `libs/`, `apps/cli/` | Apache-2.0 |
| `specs/v1.0/` (the protocol spec) | CC-BY-4.0 |
| `specs/v1.0/tests/` (conformance tests) | MIT |
| `docs/` | CC-BY-4.0 |
| `tests/`, `tools/`, `scripts/`, `infra/` | Apache-2.0 |

Backed by binding architectural commitments P1 (CLA with broad sublicensing), P2 (§6 anti-tivoization for the GUI), P3 (public protocol).

## Alternatives considered

| Option | Pros | Cons | Rejected because |
|---|---|---|---|
| GPL the whole stack | zero legal risk on combined-work question | loses backend-license optionality; cuts off later commercial-license path | counsel cleared the aggregate position |
| MIT all permissive workspaces | maximum reuse | weaker patent protection than Apache-2.0 | Apache's patent grant is materially stronger |
| Proprietary backend, GPL GUI | maximum commercial flexibility | violates GPL aggregate position (counsel: proprietary backend bundled with GPL GUI installer would weaken the separate-works argument) | unacceptable legal risk |
| Replace en-croissant with non-GPL GUI | avoids GPL entirely | months of work; en-croissant is the strongest available chess GUI base | counsel cleared the boundary; no rebuild needed |

## Consequences

### Positive

- Backend remains under a permissive license that can be embedded by commercial or proprietary downstreams.
- GUI honors its inherited GPL-3.0 obligations; users get full GPL freedoms including §6.
- Protocol is CC-BY-4.0 so third parties can implement either side without license entanglement.

### Negative / accepted tradeoffs

- P1, P2, P3 must remain in force *forever*. If the project ever drops them, the separate-works argument weakens.
- CLA bot infrastructure must be in place before the first external Backend PR. (Tracked: ADR follow-up below.)
- The auto-updater cannot perform binary-identity checks at GUI launch. (Tracked: `BUILDING.md` documents this.)

### Follow-up actions

- Wire CLA bot into CI before first external PR is accepted to `services/` / `libs/` / `apps/cli/` (Phase 1).
- Add CI test that asserts the GUI build does not perform binary-identity verification at launch (Phase 1).
- Add CI test that asserts each workspace's package metadata declares the license required by this ADR (Phase 1).

## References

- `docs/13_review_response/legal-questions-brief.md`
- `docs/13_review_response/legal-opinion-integration.md`
- `docs/13_review_response/legal-protocol-assessment-received.md`
- `LICENSING.md` (live state)
