#!/usr/bin/env python3
"""Validate that production D1 is the expected empty cutover target."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cloudflare.production_migration.contract import (
    CONTRACT_VERSION,
    MIGRATED_TABLES,
    REFERENCE_TABLES,
    TRANSIENT_TABLES,
)
from scripts.cloudflare.production_migration.database import (
    apply_d1_migrations,
    quote_identifier,
    table_fingerprint,
    table_names,
    table_schema,
)


EXPECTED_DATA_TABLES = set(MIGRATED_TABLES) | REFERENCE_TABLES | TRANSIENT_TABLES
EMPTY_TABLES = set(MIGRATED_TABLES) | TRANSIENT_TABLES
VERSIONED_TABLES = REFERENCE_TABLES | {"id_sequences"}


def validate_export(export_path: Path, migrations_dir: Path) -> dict:
    target = sqlite3.connect(":memory:")
    expected = sqlite3.connect(":memory:")
    target.row_factory = sqlite3.Row
    expected.row_factory = sqlite3.Row
    try:
        target.executescript(export_path.read_bytes().decode("utf-8"))
        apply_d1_migrations(expected, migrations_dir)
        _check_integrity(target)
        _check_required_tables(target)
        _check_schema(target, expected)
        _check_empty_tables(target)
        _check_versioned_data(target, expected)
    finally:
        target.close()
        expected.close()
    return {
        "status": "passed",
        "contract_version": CONTRACT_VERSION,
        "schema": "ok",
        "foreign_keys": "ok",
        "migrated_tables_empty": "ok",
        "transient_tables_empty": "ok",
        "versioned_reference_data": "ok",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def _check_integrity(connection: sqlite3.Connection) -> None:
    if [row[0] for row in connection.execute("PRAGMA integrity_check")] != ["ok"]:
        raise RuntimeError("D1 cutover target failed integrity validation")
    if list(connection.execute("PRAGMA foreign_key_check")):
        raise RuntimeError("D1 cutover target has foreign-key violations")


def _check_required_tables(connection: sqlite3.Connection) -> None:
    required = EXPECTED_DATA_TABLES | {"id_sequences"}
    missing = sorted(required - table_names(connection))
    if missing:
        raise RuntimeError(f"D1 cutover target is missing tables: {missing}")


def _check_schema(target: sqlite3.Connection, expected: sqlite3.Connection) -> None:
    tables = EXPECTED_DATA_TABLES | {"id_sequences"}
    mismatches = sorted(
        table
        for table in tables
        if table_schema(target, table) != table_schema(expected, table)
    )
    if mismatches:
        raise RuntimeError(f"D1 cutover target schema mismatch: {mismatches}")


def _check_empty_tables(connection: sqlite3.Connection) -> None:
    nonempty = sorted(
        table
        for table in EMPTY_TABLES
        if connection.execute(
            f"SELECT 1 FROM {quote_identifier(table)} LIMIT 1"
        ).fetchone()
    )
    if nonempty:
        raise RuntimeError(f"D1 cutover target contains application data: {nonempty}")


def _check_versioned_data(
    target: sqlite3.Connection, expected: sqlite3.Connection
) -> None:
    mismatches = sorted(
        table
        for table in VERSIONED_TABLES
        if table_fingerprint(target, table) != table_fingerprint(expected, table)
    )
    if mismatches:
        raise RuntimeError(f"D1 cutover target versioned data mismatch: {mismatches}")


def _write_evidence(path: Path, evidence: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--d1-export", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument(
        "--migrations-dir", type=Path, default=ROOT / "migrations" / "d1"
    )
    args = parser.parse_args()
    evidence = validate_export(args.d1_export, args.migrations_dir)
    _write_evidence(args.evidence, evidence)
    print("Production D1 is the expected empty cutover target.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
