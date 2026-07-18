import sqlite3
from typing import Any, Sequence

from .database_gateway import (
    DatabaseBatchResult,
    DatabaseParams,
    DatabaseStatement,
    MutationMetadata,
)


class SQLiteGateway:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def fetch_one(self, sql: str, params: DatabaseParams = ()) -> dict[str, Any] | None:
        row = self._connection.execute(sql, params).fetchone()
        return _row_to_dict(row) if row is not None else None

    def fetch_all(self, sql: str, params: DatabaseParams = ()) -> list[dict[str, Any]]:
        rows = self._connection.execute(sql, params).fetchall()
        return [_row_to_dict(row) for row in rows]

    def execute(self, sql: str, params: DatabaseParams = ()) -> MutationMetadata:
        with self._connection:
            cursor = self._connection.execute(sql, params)
        return _mutation_metadata(cursor)

    def batch(
        self, statements: Sequence[DatabaseStatement]
    ) -> list[DatabaseBatchResult]:
        results = []
        with self._connection:
            for statement in statements:
                cursor = self._connection.execute(statement.sql, statement.params)
                rows = [_row_to_dict(row) for row in cursor.fetchall()]
                results.append(
                    DatabaseBatchResult(
                        rows=rows,
                        metadata=_mutation_metadata(cursor),
                    )
                )
        return results

    def allocate_id(self, sequence: str) -> int:
        with self._connection:
            row = self._connection.execute(
                """
                update id_sequences
                set next_value=next_value + 1
                where name=?
                returning next_value - 1 as id
                """,
                (sequence,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown ID sequence: {sequence}")
        return int(row["id"])

    def close(self):
        self._connection.close()


def _row_to_dict(row: sqlite3.Row | Sequence[Any]) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    raise TypeError("SQLiteGateway requires sqlite3.Row results")


def _mutation_metadata(cursor: sqlite3.Cursor) -> MutationMetadata:
    changes = max(cursor.rowcount, 0)
    last_row_id = cursor.lastrowid if cursor.lastrowid else None
    return MutationMetadata(
        changes=changes,
        last_row_id=last_row_id,
        rows_written=changes,
    )
