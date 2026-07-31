"""Upgrade a private source snapshot without touching the live database."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class SourceMigrationError(RuntimeError):
    """Raised when a source snapshot cannot be upgraded deterministically."""


def apply_pending_source_migrations(database_path: Path, migrations_dir: Path) -> dict:
    migration_paths = sorted(migrations_dir.glob("*.sql"))
    if not migration_paths:
        raise SourceMigrationError("No source SQLite migrations were found.")

    connection = sqlite3.connect(database_path)
    try:
        applied = _applied_migrations(connection)
        _check_linear_history(applied, migration_paths)
        pending = [path for path in migration_paths if path.name not in applied]
        for path in pending:
            _apply_migration(connection, path)
        _validate_upgraded_snapshot(connection)
    finally:
        connection.close()

    return {
        "from_migration": migration_paths[len(applied) - 1].name if applied else None,
        "to_migration": migration_paths[-1].name,
        "applied": [path.name for path in pending],
    }


def _applied_migrations(connection: sqlite3.Connection) -> set[str]:
    table = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if table is None:
        raise SourceMigrationError("Source database has no schema_migrations table.")
    return {
        row[0] for row in connection.execute("SELECT filename FROM schema_migrations")
    }


def _check_linear_history(applied: set[str], paths: list[Path]) -> None:
    available = [path.name for path in paths]
    unknown = sorted(applied - set(available))
    if unknown:
        raise SourceMigrationError(f"Unknown applied source migrations: {unknown}")
    expected = set(available[: len(applied)])
    if applied != expected:
        missing = sorted(expected - applied)
        unexpected = sorted(applied - expected)
        raise SourceMigrationError(
            "Source migration history is not a contiguous prefix; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _apply_migration(connection: sqlite3.Connection, path: Path) -> None:
    try:
        connection.executescript(path.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,)
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _validate_upgraded_snapshot(connection: sqlite3.Connection) -> None:
    integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        raise SourceMigrationError(f"Upgraded snapshot integrity failed: {integrity}")
    foreign_keys = list(connection.execute("PRAGMA foreign_key_check"))
    if foreign_keys:
        raise SourceMigrationError(
            f"Upgraded snapshot has {len(foreign_keys)} foreign-key violation(s)."
        )
