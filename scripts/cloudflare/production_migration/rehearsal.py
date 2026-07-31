"""Apply the export locally and reconcile every migrated table."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .contract import MIGRATED_TABLES, SEQUENCE_TABLES
from .database import apply_d1_migrations, table_fingerprint


def rehearse(
    source: sqlite3.Connection, export_path: Path, migrations_dir: Path
) -> dict:
    target = sqlite3.connect(":memory:")
    target.row_factory = sqlite3.Row
    try:
        apply_d1_migrations(target, migrations_dir)
        target.executescript(export_path.read_bytes().decode("utf-8"))
        target.commit()
        result = reconcile_source(source, target)
        return {
            "status": "passed",
            **result,
        }
    finally:
        target.close()


def reconcile_source(source: sqlite3.Connection, target: sqlite3.Connection) -> dict:
    fingerprints = {}
    for table in MIGRATED_TABLES:
        source_value = table_fingerprint(source, table)
        target_value = table_fingerprint(target, table)
        if source_value != target_value:
            raise RuntimeError(
                f"Local D1 rehearsal mismatch for {table}: "
                f"source={source_value}, target={target_value}"
            )
        fingerprints[table] = source_value
    _check_foreign_keys(target)
    sequences = _check_sequences(target)
    return {
        "tables": fingerprints,
        "foreign_keys": "ok",
        "id_sequences": sequences,
    }


def reconcile_manifest(manifest: dict, target: sqlite3.Connection) -> dict:
    fingerprints = {}
    for table in MIGRATED_TABLES:
        expected = manifest["migrated_tables"][table]
        actual = table_fingerprint(target, table)
        if actual != expected:
            raise RuntimeError(
                f"Remote D1 rehearsal mismatch for {table}: "
                f"expected={expected}, actual={actual}"
            )
        fingerprints[table] = actual
    _check_foreign_keys(target)
    sequences = _check_sequences(target)
    return {
        "tables": fingerprints,
        "foreign_keys": "ok",
        "id_sequences": sequences,
    }


def _check_foreign_keys(connection: sqlite3.Connection) -> None:
    failures = list(connection.execute("PRAGMA foreign_key_check"))
    if failures:
        raise RuntimeError(
            f"Local D1 rehearsal has {len(failures)} foreign-key violation(s)."
        )


def _check_sequences(connection: sqlite3.Connection) -> dict:
    values = {}
    for table in SEQUENCE_TABLES:
        actual = connection.execute(
            "SELECT next_value FROM id_sequences WHERE name=?", (table,)
        ).fetchone()[0]
        expected = connection.execute(
            f'SELECT COALESCE(MAX(id), 0) + 1 FROM "{table}"'
        ).fetchone()[0]
        if actual != expected:
            raise RuntimeError(
                f"Sequence mismatch for {table}: expected {expected}, got {actual}"
            )
        values[table] = actual
    return values
