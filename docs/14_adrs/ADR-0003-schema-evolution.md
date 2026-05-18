# ADR-0003: Schema evolution (SQLite migrations + Pydantic versioning)

- **Status**: accepted
- **Date**: 2026-05-18
- **Deciders**: project owner

## Context

User data persists across versions. We must evolve SQLite schemas and Pydantic models without losing user data, without forcing backups before every update, and without coupling client-visible API versions to internal storage versions.

## Decision

1. **SQLite migrations**: forward-only, numbered. `libs/storage/migrations/0001_initial.sql`, `0002_*.sql`, etc. On startup, the backend reads `PRAGMA user_version`, runs all migrations with number > current, and commits each in its own transaction. No down-migrations. Tested by a CI suite that exercises *every* historical migration path against a fresh database.
2. **Backup before risky migrations**. A migration may declare itself "risky" (column drop, type change, large rewrite) via a leading SQL comment `-- chess_coach:risky`. The runtime copies the database file before applying any risky migration. Backups land in `${CHESS_COACH_DATA_DIR}/backups/sqlite-{user_version}-{timestamp}.db` and are retained per the user's backup-retention setting.
3. **Pydantic model versioning**. Storage models live in `chess_coach.storage.models.v{N}`. When a model changes shape incompatibly, a new version is added; the old one is retained until migrations have moved all live data over. Code at any moment imports the *current* version explicitly (`from chess_coach.storage.models.v2 import GameRow`).
4. **API model independence**. Storage models and protocol/API models are **separate** Pydantic models, even when shapes coincide. Conversion functions live in `chess_coach.gateway.adapters`. This lets us refactor storage without breaking the public protocol and vice versa.
5. **Telemetry-free migration**. Migrations log structured progress to stderr; they do not call any LLM, network, or external service.

## Alternatives considered

| Option | Pros | Cons | Rejected because |
|---|---|---|---|
| Alembic | mature | overkill for single-database SQLite-only setup | hand-rolled migrations are ~200 LOC |
| Down-migrations | reversibility | doubles maintenance burden; rarely used in practice | not worth it for single-user app |
| Skip versioning, ALTER TABLE in code | fewer files | impossible to reason about state | unsafe |
| Storage = API model | less code | tightly couples internal layout to public protocol | breaks the layered separation |

## Consequences

### Positive

- User data preserved across updates.
- Schema rollbacks possible via backups when needed (manual, but available).
- Storage refactors don't break clients.

### Negative / accepted tradeoffs

- More files than "just one models.py." Mitigation: clear directory layout; storage `__init__.py` re-exports current version.
- Risky-migration backups consume disk. Mitigation: retention policy + a one-shot "clean old backups" admin command.

### Follow-up actions

- Author `libs/storage/migrate.py` runner in Phase 1.
- Author `0001_initial.sql` for Phase 1's Stockfish + games + analysis tables.
- Wire migration runner into gateway startup.

## References

- `docs/04_database/database-decision.md`
- `docs/02_modules/module-decomposition.md` § memory+kb
