# JSON Schemas — Protocol v1.0

One `*.schema.json` per documented request/response shape, drawing from spec §3 (Envelope Conventions) and §4 (REST Endpoints).

## Authoring policy

- Schemas are **generated** from the Pydantic v2 models in `libs/protocol_types/` at the gateway build step, then committed here.
- Hand-edits are not accepted; if a schema is wrong, fix the Pydantic model and regenerate.
- The CI build asserts that the schemas committed here match the regenerated set.

## Use by third parties

A third-party implementation in any language can ingest these schemas with the standard tooling for that language (e.g. `quicktype`, `datamodel-codegen`, `json-schema-to-typescript`). License is CC-BY-4.0 same as the spec document; no special permission needed for derivative works.

Schemas will be authored at Phase 1 once the Pydantic models exist.
