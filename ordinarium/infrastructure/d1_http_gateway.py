from typing import Any, Sequence

import requests

from .database_gateway import (
    DatabaseBatchResult,
    DatabaseParams,
    DatabaseStatement,
    MutationMetadata,
)


class D1GatewayError(RuntimeError):
    pass


class D1HttpGateway:
    def __init__(
        self,
        service_url: str,
        *,
        timeout_seconds: float = 30,
        max_response_bytes: int = 5 * 1024 * 1024,
        session: requests.Session | None = None,
    ):
        self._service_url = service_url
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._session = session or requests.Session()

    def fetch_one(self, sql: str, params: DatabaseParams = ()) -> dict[str, Any] | None:
        payload = self._request("fetch_one", sql=sql, params=params)
        row = payload.get("row")
        if row is not None and not isinstance(row, dict):
            raise D1GatewayError("D1 bridge returned an invalid row.")
        return row

    def fetch_all(self, sql: str, params: DatabaseParams = ()) -> list[dict[str, Any]]:
        payload = self._request("fetch_all", sql=sql, params=params)
        return _rows(payload)

    def execute(self, sql: str, params: DatabaseParams = ()) -> MutationMetadata:
        payload = self._request("execute", sql=sql, params=params)
        return _metadata(payload.get("metadata"))

    def batch(
        self, statements: Sequence[DatabaseStatement]
    ) -> list[DatabaseBatchResult]:
        payload = self._request(
            "batch",
            statements=[
                {"sql": statement.sql, "params": list(statement.params)}
                for statement in statements
            ],
        )
        raw_results = payload.get("results")
        if not isinstance(raw_results, list) or any(
            not isinstance(result, dict) for result in raw_results
        ):
            raise D1GatewayError("D1 bridge returned invalid batch results.")
        return [
            DatabaseBatchResult(
                rows=_rows(result),
                metadata=_metadata(result.get("metadata")),
            )
            for result in raw_results
        ]

    def allocate_id(self, sequence: str) -> int:
        payload = self._request("allocate_id", sequence=sequence)
        allocated_id = payload.get("id")
        if not isinstance(allocated_id, int) or isinstance(allocated_id, bool):
            raise D1GatewayError("D1 bridge returned an invalid allocated ID.")
        return allocated_id

    def _request(self, operation: str, **values):
        body = {"operation": operation, **values}
        if "params" in body:
            body["params"] = list(body["params"])
        try:
            response = self._session.post(
                self._service_url,
                json=body,
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as exc:
            raise D1GatewayError("D1 bridge is unavailable.") from exc
        if len(response.content) > self._max_response_bytes:
            raise D1GatewayError("D1 bridge response exceeded the size limit.")
        try:
            payload = response.json()
        except requests.JSONDecodeError as exc:
            raise D1GatewayError("D1 bridge returned invalid JSON.") from exc
        if response.status_code != 200 or not isinstance(payload, dict):
            raise D1GatewayError(f"D1 bridge returned HTTP {response.status_code}.")
        if payload.get("ok") is not True:
            error = payload.get("error") or "unknown_error"
            raise D1GatewayError(f"D1 bridge operation failed: {error}.")
        return payload


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise D1GatewayError("D1 bridge returned invalid rows.")
    return rows


def _metadata(value: Any) -> MutationMetadata:
    if not isinstance(value, dict):
        raise D1GatewayError("D1 bridge returned invalid mutation metadata.")
    return MutationMetadata(
        changes=_optional_int(value.get("changes")) or 0,
        last_row_id=_optional_int(value.get("last_row_id")),
        rows_read=_optional_int(value.get("rows_read")),
        rows_written=_optional_int(value.get("rows_written")),
        duration_ms=_optional_float(value.get("duration_ms")),
    )


def _optional_int(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _optional_float(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None
