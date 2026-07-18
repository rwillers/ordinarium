from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence


DatabaseParams = Sequence[Any]


@dataclass(frozen=True)
class DatabaseStatement:
    sql: str
    params: DatabaseParams = ()


@dataclass(frozen=True)
class MutationMetadata:
    changes: int = 0
    last_row_id: int | None = None
    rows_read: int | None = None
    rows_written: int | None = None
    duration_ms: float | None = None


@dataclass(frozen=True)
class DatabaseBatchResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    metadata: MutationMetadata = field(default_factory=MutationMetadata)


class DatabaseGateway(Protocol):
    def fetch_one(
        self, sql: str, params: DatabaseParams = ()
    ) -> dict[str, Any] | None: ...

    def fetch_all(
        self, sql: str, params: DatabaseParams = ()
    ) -> list[dict[str, Any]]: ...

    def execute(self, sql: str, params: DatabaseParams = ()) -> MutationMetadata: ...

    def batch(
        self, statements: Sequence[DatabaseStatement]
    ) -> list[DatabaseBatchResult]: ...

    def allocate_id(self, sequence: str) -> int: ...
