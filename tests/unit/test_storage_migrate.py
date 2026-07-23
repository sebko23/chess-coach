"""Tests for the migration runner."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from chess_coach.storage import (
    discover_migrations,
    get_user_version,
    migrate,
)


class TestDiscovery:
    def test_at_least_one_migration_exists(self) -> None:
        ms = discover_migrations()
        assert ms, "no migrations found"
        assert ms[0].version == 1
        assert ms[0].name.startswith("0001_")

    def test_versions_are_contiguous(self) -> None:
        ms = discover_migrations()
        versions = [m.version for m in ms]
        assert versions == list(range(1, len(versions) + 1))

    def test_initial_migration_is_not_risky(self) -> None:
        ms = discover_migrations()
        assert ms[0].is_risky is False


class TestMigrate:
    def test_creates_db_and_applies_initial(self, tmp_path: Path) -> None:
        db = tmp_path / "sub" / "chess_coach.db"
        applied = migrate(db, backups_dir=tmp_path / "backups")
        assert db.exists()
        assert len(applied) >= 1
        # user_version is bumped to the highest applied migration
        with sqlite3.connect(str(db)) as conn:
            assert get_user_version(conn) == applied[-1].version

    def test_idempotent_when_up_to_date(self, tmp_path: Path) -> None:
        db = tmp_path / "chess_coach.db"
        first = migrate(db)
        second = migrate(db)
        assert first  # something happened first time
        assert second == []  # nothing happened second time

    def test_meta_table_has_protocol_range(self, tmp_path: Path) -> None:
        db = tmp_path / "chess_coach.db"
        migrate(db)
        with sqlite3.connect(str(db)) as conn:
            rows = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        assert rows["protocol_min"] == "1.0.0"
        assert rows["protocol_max"] == "1.0.0"

    def test_wal_mode_after_migrate(self, tmp_path: Path) -> None:
        db = tmp_path / "chess_coach.db"
        migrate(db)
        # Re-open and inspect.
        with sqlite3.connect(str(db)) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
