from .database_gateway import DatabaseStatement, MutationMetadata


class GatewayCursor:
    def __init__(self, rows=None, metadata=None):
        self._rows = list(rows or [])
        self._index = 0
        self._metadata = metadata or MutationMetadata()

    @property
    def lastrowid(self):
        return self._metadata.last_row_id

    @property
    def rowcount(self):
        return self._metadata.changes

    def fetchone(self):
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self):
        rows = self._rows[self._index :]
        self._index = len(self._rows)
        return rows


class GatewayConnection:
    """Small DB-API compatibility layer for the final PCO port boundary."""

    def __init__(self, gateway):
        self._gateway = gateway

    def execute(self, sql, params=()):
        if _returns_rows(sql):
            return GatewayCursor(rows=self._gateway.fetch_all(sql, params))
        return GatewayCursor(metadata=self._gateway.execute(sql, params))

    def executemany(self, sql, params):
        statements = [DatabaseStatement(sql, values) for values in params]
        if not statements:
            return GatewayCursor()
        results = self._gateway.batch(statements)
        changes = sum(result.metadata.changes for result in results)
        last_row_id = results[-1].metadata.last_row_id if results else None
        return GatewayCursor(
            metadata=MutationMetadata(changes=changes, last_row_id=last_row_id)
        )

    def batch(self, statements):
        """Execute an ordered, atomic gateway batch."""
        return self._gateway.batch(statements)

    def commit(self):
        return None

    def rollback(self):
        return None


def _returns_rows(sql):
    statement = sql.lstrip().lower()
    return statement.startswith(("select", "with", "explain"))
