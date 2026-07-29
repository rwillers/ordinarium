"""Safety checks that must pass before production data is exported."""

from __future__ import annotations

import sqlite3
import time

from .contract import (
    CLAIM_COLUMNS,
    KNOWN_SOURCE_TABLES,
    MIGRATED_TABLES,
    TERMINAL_STATUSES,
)
from .database import quote_identifier, table_names, table_schema


class PreflightError(RuntimeError):
    """Raised when the source is unsafe or incompatible with the D1 target."""


def run_preflight(
    source: sqlite3.Connection, target_schema: sqlite3.Connection
) -> dict:
    checks = {
        "integrity": _check_integrity(source),
        "foreign_keys": _check_foreign_keys(source),
        "known_tables": _check_known_tables(source),
        "schema_parity": _check_schema_parity(source, target_schema),
        "pco_work_drained": _check_pco_work(source),
        "claims_released": _check_claims(source),
        "service_leases_drained": _check_service_leases(source),
    }
    return checks


def _check_integrity(connection: sqlite3.Connection) -> str:
    rows = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    if rows != ["ok"]:
        raise PreflightError(f"SQLite integrity_check failed: {rows}")
    return "ok"


def _check_foreign_keys(connection: sqlite3.Connection) -> str:
    failures = list(connection.execute("PRAGMA foreign_key_check"))
    if failures:
        raise PreflightError(
            f"SQLite foreign_key_check found {len(failures)} violation(s)."
        )
    return "ok"


def _check_known_tables(connection: sqlite3.Connection) -> str:
    unknown = sorted(table_names(connection) - KNOWN_SOURCE_TABLES)
    if unknown:
        raise PreflightError(f"Unknown source tables require review: {unknown}")
    return "ok"


def _check_schema_parity(source: sqlite3.Connection, target: sqlite3.Connection) -> str:
    source_tables = table_names(source)
    target_tables = table_names(target)
    missing_source = sorted(set(MIGRATED_TABLES) - source_tables)
    missing_target = sorted(set(MIGRATED_TABLES) - target_tables)
    if missing_source or missing_target:
        raise PreflightError(
            "Migration tables are missing; "
            f"source={missing_source}, target={missing_target}"
        )
    mismatches = [
        table
        for table in MIGRATED_TABLES
        if table_schema(source, table) != table_schema(target, table)
    ]
    if mismatches:
        raise PreflightError(f"Source/D1 schema mismatch for: {mismatches}")
    return "ok"


def _check_pco_work(connection: sqlite3.Connection) -> str:
    unfinished = {}
    for table, terminal in TERMINAL_STATUSES.items():
        placeholders = ", ".join("?" for _ in terminal)
        row = connection.execute(
            f"""
            SELECT COUNT(*) FROM {quote_identifier(table)}
            WHERE status NOT IN ({placeholders})
            """,
            tuple(sorted(terminal)),
        ).fetchone()
        if row[0]:
            unfinished[table] = row[0]
    if unfinished:
        raise PreflightError(f"Planning Center work is not drained: {unfinished}")
    return "ok"


def _check_claims(connection: sqlite3.Connection) -> str:
    claimed = {}
    for table, columns in CLAIM_COLUMNS.items():
        condition = " OR ".join(
            f"{quote_identifier(column)} IS NOT NULL" for column in columns
        )
        count = connection.execute(
            f"SELECT COUNT(*) FROM {quote_identifier(table)} WHERE {condition}"
        ).fetchone()[0]
        if count:
            claimed[table] = count
    if claimed:
        raise PreflightError(f"Planning Center claims remain active: {claimed}")
    return "ok"


def _check_service_leases(connection: sqlite3.Connection) -> str:
    count = connection.execute(
        """
        SELECT COUNT(*) FROM pco_service_sync_leases
        WHERE claim_expires_at > ?
        """,
        (int(time.time()),),
    ).fetchone()[0]
    if count:
        raise PreflightError(f"Planning Center service leases remain active: {count}")
    return "ok"
