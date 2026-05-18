"""SQLite migration runner.

ADR-0003: forward-only, numbered migrations. On startup we read the database's
``PRAGMA user_version``, apply every migration with number > current, each in
its own transaction, and bump ``user_version`` after success.

Migrations live in ``libs/chess_coach/storage/migrations/`` named
``NNNN_short_slug.sql`` where NNNN is a zero-padded monotonically increasing
integer starting at 0001.

A migration may declare itself "risky" (column drop, type change, large
rewrite) by including the literal directive ``-- chess_coach:risky`` on a line
of its own. The runner copies the database file to
``${CHESS_COACH_DATA_DIR}/backups/sqlite-{user_version}-{timestamp}.db``
before applying any risky migration.

No down-migrations.
"""
from __future__ import annotations

import logging
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from chess_coach.errors import MigrationFailedError

logger = logging.getLogger(__name__)

_MIGRATION_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
_RISKY_DIRECTIVE = "-- chess_coach:risky"


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str  # without the .sql suffix
    sql: str

    @property
    def is_risky(self) -> bool:
        return any(
            line.strip() == _RISKY_DIRECTIVE for line in self.sql.splitlines()
        )


def discover_migrations() -> list[Migration]:
    """Load all migrations from the package's ``migrations/`` directory.

    Sorted ascending by version. Validates that versions are contiguous from 1.
    """
    pkg = files("chess_coach.storage.migrations")
    migrations: list[Migration] = []
    for entry in sorted(pkg.iterdir(), key=lambda e: e.name):  # type: ignore[attr-defined]
        m = _MIGRATION_RE.match(entry.name)
        if not m:
            continue
        version = int(m.group(1))
        sql = entry.read_text(encoding="utf-8")
        migrations.append(
            Migration(version=version, name=entry.name[:-4], sql=sql)
        )
    if migrations:
        expected = list(range(1, len(migrations) + 1))
        actual = [m.version for m in migrations]
        if expected != actual:
            raise MigrationFailedError(
                f"Migration versions are non-contiguous; expected {expected}, got {actual}"
            )
    return migrations


def get_user_version(conn: sqlite3.Connection) -> int:
    cur = conn.execute("PRAGMA user_version")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def set_user_version(conn: sqlite3.Connection, version: int) -> None:
    # PRAGMA does not accept parameters, but the value is integer-validated.
    conn.execute(f"PRAGMA user_version = {int(version)}")


def _backup_database(db_path: Path, backups_dir: Path, current_version: int) -> Path:
    backups_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backups_dir / f"sqlite-{current_version:04d}-{ts}.db"
    # Use sqlite's online backup API rather than file copy, so we don't fight
    # WAL or in-flight writes.
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(backup_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return backup_path


def migrate(
    db_path: Path,
    *,
    backups_dir: Path | None = None,
) -> list[Migration]:
    """Run all pending migrations against the database at ``db_path``.

    Returns the list of migrations that were applied (empty if up-to-date).
    Creates the database file if it does not exist.

    On failure, raises :class:`MigrationFailedError`. The error includes the
    failing migration's name in ``details``.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    migrations = discover_migrations()
    applied: list[Migration] = []

    conn = sqlite3.connect(str(db_path), isolation_level=None)  # autocommit; we control TX
    try:
        # Sensible defaults for our use; the gateway later opens its own connections.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")

        current = get_user_version(conn)
        pending = [m for m in migrations if m.version > current]
        if not pending:
            logger.info("storage.migrate: up-to-date at user_version=%d", current)
            return []

        logger.info(
            "storage.migrate: applying %d migration(s); current=%d, target=%d",
            len(pending),
            current,
            pending[-1].version,
        )

        for m in pending:
            if m.is_risky and backups_dir is not None:
                backup_path = _backup_database(db_path, backups_dir, current)
                logger.warning(
                    "storage.migrate: risky migration %s; backed up to %s",
                    m.name,
                    backup_path,
                )
            # NOTE: sqlite3.Connection.executescript() issues an *implicit*
            # COMMIT before running the script, which would silently end any
            # transaction we opened with conn.execute("BEGIN"). We therefore
            # build a single script that contains the BEGIN, the migration
            # body, the user_version bump, and the COMMIT in one piece.
            full_script = (
                "BEGIN;\n"
                + m.sql.rstrip()
                + f"\nPRAGMA user_version = {int(m.version)};\n"
                + "COMMIT;\n"
            )
            try:
                conn.executescript(full_script)
            except Exception as exc:
                # If executescript fails partway through, the connection is
                # left without an active transaction; ROLLBACK is best-effort.
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise MigrationFailedError(
                    f"Migration {m.name} failed: {exc}",
                    details={"migration": m.name, "version": m.version},
                ) from exc
            applied.append(m)
            current = m.version
            logger.info("storage.migrate: applied %s -> user_version=%d", m.name, current)
        return applied
    finally:
        conn.close()


def ensure_writable(db_path: Path) -> None:
    """Best-effort sanity check that ``db_path``'s directory is writable.

    Raises :class:`MigrationFailedError` with details if not.
    """
    parent = db_path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        probe = parent / ".write-probe"
        probe.write_text("x")
        probe.unlink()
    except OSError as exc:
        raise MigrationFailedError(
            f"Database directory not writable: {parent} ({exc})",
            details={"path": str(parent)},
        ) from exc


# Convenience for tests / scripts
def rebuild_clean(db_path: Path) -> None:
    """Remove the database file and rerun migrations from scratch."""
    if db_path.exists():
        # Also remove SQLite WAL sidecars if present.
        for suffix in ("", "-wal", "-shm"):
            sidecar = db_path.with_suffix(db_path.suffix + suffix) if suffix else db_path
            if sidecar.exists():
                sidecar.unlink()
    migrate(db_path)


__all__ = [
    "Migration",
    "discover_migrations",
    "ensure_writable",
    "get_user_version",
    "migrate",
    "rebuild_clean",
    "set_user_version",
]
