"""Create a D1-compatible, deterministic SQL data export."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .contract import MIGRATED_TABLES, SEQUENCE_TABLES
from .database import iter_table_rows, quote_identifier, table_columns

MAX_D1_STATEMENT_BYTES = 100_000


def write_export(connection: sqlite3.Connection, destination: Path) -> None:
    temporary = destination.with_suffix(".sql.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                "-- Generated production data import for Cloudflare D1.\n"
                "-- Apply only after the versioned D1 migrations, against an empty target.\n\n"
                "PRAGMA defer_foreign_keys = true;\n"
            )
            for table in MIGRATED_TABLES:
                _write_table(handle, connection, table)
            _write_sequence_updates(handle)
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return f"X'{value.hex()}'"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _write_table(handle, connection: sqlite3.Connection, table: str) -> None:
    columns = tuple(sorted(table_columns(connection, table)))
    column_sql = ", ".join(quote_identifier(column) for column in columns)
    handle.write(f"\n-- {table}\n")
    for row in iter_table_rows(connection, table):
        values_sql = ", ".join(sql_literal(value) for value in row)
        statement = (
            f"INSERT INTO {quote_identifier(table)} ({column_sql}) "
            f"VALUES ({values_sql});\n"
        )
        if len(statement.encode("utf-8")) > MAX_D1_STATEMENT_BYTES:
            raise ValueError(f"A {table} row exceeds D1's 100 KB SQL statement limit.")
        handle.write(statement)


def _write_sequence_updates(handle) -> None:
    handle.write("\n-- Reconcile numeric ID allocation after explicit-ID inserts.\n")
    for table in SEQUENCE_TABLES:
        quoted = quote_identifier(table)
        handle.write(
            'UPDATE "id_sequences" '
            f"SET next_value=(SELECT COALESCE(MAX(id), 0) + 1 FROM {quoted}) "
            f"WHERE name={sql_literal(table)};\n"
        )
