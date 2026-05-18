# `libs/` — Shared libraries

**License**: Apache-2.0.

Libraries used by multiple services. Phase-1 packages planned:

| Library | Purpose |
|---|---|
| `chess_coach.protocol_types` | Pydantic v2 models that mirror `specs/v1.0/`. Source of truth for JSON Schemas. |
| `chess_coach.errors` | Typed exception hierarchy (see ADR-0002). |
| `chess_coach.storage` | SQLite migrations runner + storage models (see ADR-0003). |
| `chess_coach.uci` | Async UCI client (process management, parsing). |
| `chess_coach.testkit` | Test utilities including the conformance harness. |
