"""SQLite inspection and deterministic row fingerprint helpers."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


def connect_read_only(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"SQLite database not found: {resolved}")
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def apply_d1_migrations(connection: sqlite3.Connection, directory: Path) -> None:
    for path in sorted(directory.glob("*.sql")):
        connection.executescript(path.read_text(encoding="utf-8"))


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name FROM sqlite_schema
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """
    )
    return {row[0] for row in rows}


def table_columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(row["name"] for row in _table_info(connection, table))


def table_schema(connection: sqlite3.Connection, table: str) -> tuple[tuple, ...]:
    """Return the structural properties that constrain explicit-row imports."""
    return tuple(
        sorted(
            (
                row["name"],
                _type_affinity(row["type"]),
                row["notnull"],
                row["pk"],
            )
            for row in _table_info(connection, table)
        )
    )


def _type_affinity(declared_type: str) -> str:
    value = declared_type.strip().upper()
    if "INT" in value:
        return "INTEGER"
    if any(token in value for token in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if not value or "BLOB" in value:
        return "BLOB"
    if any(token in value for token in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def iter_table_rows(connection: sqlite3.Connection, table: str):
    columns = tuple(sorted(table_columns(connection, table)))
    primary_key = tuple(
        row["name"]
        for row in sorted(_table_info(connection, table), key=lambda row: row["pk"])
        if row["pk"]
    )
    order_by = primary_key or columns
    column_sql = ", ".join(quote_identifier(column) for column in columns)
    order_sql = ", ".join(quote_identifier(column) for column in order_by)
    yield from connection.execute(
        f"SELECT {column_sql} FROM {quote_identifier(table)} ORDER BY {order_sql}"
    )


def table_fingerprint(connection: sqlite3.Connection, table: str) -> dict:
    digest = hashlib.sha256()
    count = 0
    for row in iter_table_rows(connection, table):
        digest.update(_canonical_row(row))
        digest.update(b"\n")
        count += 1
    return {"rows": count, "sha256": digest.hexdigest()}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quote_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _table_info(connection: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return list(connection.execute(f"PRAGMA table_info({quote_identifier(table)})"))


def _canonical_row(row: sqlite3.Row) -> bytes:
    values = [_canonical_value(value) for value in row]
    return json.dumps(
        values, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _canonical_value(value):
    if isinstance(value, bytes):
        return {"blob": value.hex()}
    if isinstance(value, float):
        return {"float": value.hex()}
    return value
