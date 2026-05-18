# ADR-0002: Error envelope and error-code allocation

- **Status**: accepted
- **Date**: 2026-05-18
- **Deciders**: project owner

## Context

The public protocol (`specs/v1.0/chess-coach-protocol-v1.md` §10) defines an error envelope and a list of error codes. We need an internal policy for (a) how backend code raises and shapes errors, and (b) how new error codes are allocated without breaking conformance.

## Decision

1. **Internal exception hierarchy**. Backend code raises typed exceptions from `chess_coach.errors`. Each exception class carries:
   - `code` (matches protocol §10),
   - `message` (human-readable, must not contain user-supplied content unsanitized),
   - `details` (dict of structured fields; serializable),
   - `retriable` (bool).
2. **FastAPI exception handler** (single, central) converts these to the protocol's error envelope. No ad-hoc `HTTPException` outside the gateway layer.
3. **Error code allocation**. Codes are namespaced `<category>.<subcategory>.<detail>` (e.g. `engine.timeout.deepening`, `cache.miss.transient`). Adding a code is a minor protocol version bump; renaming or removing one is a major bump.
4. **Reserved codes**. The set listed in protocol v1.0 §10 is locked. New v1.x codes go in a `CODES.md` registry file added to `specs/v1.0/CODES.md` (to be authored at Phase 1) and are listed in the changelog.
5. **Logging contract**. Every error logged at the gateway boundary includes `request_id`, `code`, and a redacted `message`; `details` is logged at debug level only (it may contain large payloads).

## Alternatives considered

| Option | Pros | Cons | Rejected because |
|---|---|---|---|
| RFC 7807 Problem Details | standard | overspecified for our needs; clients want machine-readable code first | protocol §10 is simpler |
| Numeric error codes | compact | not self-describing; painful to grep | strings are cheap |
| One catch-all `internal_error` | simple | useless for debugging or for clients implementing retry policies | clients need to distinguish retriable from terminal |

## Consequences

### Positive

- Clients have a stable, growable error vocabulary.
- Server code raises domain exceptions; envelope shape is the gateway's responsibility.
- Adding error codes is non-breaking.

### Negative / accepted tradeoffs

- `CODES.md` registry must be maintained alongside code changes; CI lint will check that new exception `code` strings exist in the registry.

### Follow-up actions

- Author `chess_coach/errors.py` skeleton in Phase 1.
- Author `specs/v1.0/CODES.md` registry in Phase 1 (mirror of protocol §10 plus growth procedure).
- Author the CI lint to enforce registry consistency.

## References

- `specs/v1.0/chess-coach-protocol-v1.md` §10 Error Codes
- `docs/02_modules/module-decomposition.md` § gateway
