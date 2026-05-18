# Protocol v1.0

Stable since 2026-05-18.

## Files

| File | Description |
|---|---|
| `chess-coach-protocol-v1.md` | The specification. Authoritative for v1.x. CC-BY-4.0. |
| `schemas/` | JSON Schemas for every documented request and response. CC-BY-4.0. |
| `tests/` | Conformance test runner and test vectors. MIT. |
| `CHANGELOG.md` | Per-version changelog. _(to be authored at Phase 1)_ |
| `CODES.md` | Error-code registry, mirroring spec §10 plus growth procedure. _(to be authored at Phase 1; see `docs/14_adrs/ADR-0002-error-envelope.md`)_ |

## Conformance

Any implementation MUST satisfy the conformance criteria in spec §12. The `tests/` runner gives automated coverage of the testable subset; some criteria (e.g. semver discipline across releases) are necessarily process-level and not directly testable.

## Reporting bugs in the spec

If you find an ambiguity, contradiction, or missing detail in the specification, please open an issue with the label `spec`. We treat spec bugs with the same priority as code bugs.
