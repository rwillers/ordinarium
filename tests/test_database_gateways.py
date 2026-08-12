import sqlite3

import pytest

from ordinarium.infrastructure import DatabaseStatement, SQLiteGateway
from ordinarium.infrastructure.d1_http_gateway import D1GatewayError, D1HttpGateway


def _sqlite_gateway():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        create table id_sequences (
          name text primary key,
          next_value integer not null
        );
        insert into id_sequences (name, next_value) values ('widgets', 4);
        create table widgets (
          id integer primary key,
          name text not null unique
        );
        """
    )
    return connection, SQLiteGateway(connection)


def test_sqlite_gateway_normalizes_reads_writes_and_ids():
    connection, gateway = _sqlite_gateway()
    try:
        metadata = gateway.execute(
            "insert into widgets (id, name) values (?, ?)", (1, "Alpha")
        )
        assert metadata.changes == 1
        assert gateway.fetch_one("select * from widgets where id=?", (1,)) == {
            "id": 1,
            "name": "Alpha",
        }
        assert gateway.fetch_all("select * from widgets") == [
            {"id": 1, "name": "Alpha"}
        ]
        assert gateway.allocate_id("widgets") == 4
        assert gateway.allocate_id("widgets") == 5
    finally:
        connection.close()


def test_sqlite_gateway_batch_is_atomic():
    connection, gateway = _sqlite_gateway()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            gateway.batch(
                [
                    DatabaseStatement(
                        "insert into widgets (id, name) values (?, ?)",
                        (1, "Same"),
                    ),
                    DatabaseStatement(
                        "insert into widgets (id, name) values (?, ?)",
                        (2, "Same"),
                    ),
                ]
            )
        assert gateway.fetch_all("select * from widgets") == []
    finally:
        connection.close()


def test_sqlite_gateway_rejects_unknown_sequence():
    connection, gateway = _sqlite_gateway()
    try:
        with pytest.raises(KeyError, match="Unknown ID sequence"):
            gateway.allocate_id("missing")
    finally:
        connection.close()


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = repr(payload).encode()

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_d1_http_gateway_normalizes_bridge_responses():
    session = _FakeSession(
        [
            _FakeResponse({"ok": True, "row": {"id": 7, "name": "Alpha"}}),
            _FakeResponse(
                {
                    "ok": True,
                    "rows": [{"id": 7, "name": "Alpha"}],
                    "metadata": {
                        "changes": 0,
                        "last_row_id": 0,
                        "rows_read": 1,
                        "rows_written": 0,
                        "duration_ms": 0.2,
                    },
                }
            ),
            _FakeResponse(
                {
                    "ok": True,
                    "metadata": {
                        "changes": 1,
                        "last_row_id": 7,
                        "rows_written": 1,
                    },
                }
            ),
            _FakeResponse({"ok": True, "id": 8}),
        ]
    )
    gateway = D1HttpGateway("http://d1.internal/query", session=session)

    assert gateway.fetch_one("select * from widgets where id=?", (7,))["name"] == (
        "Alpha"
    )
    assert gateway.fetch_all("select * from widgets") == [{"id": 7, "name": "Alpha"}]
    assert gateway.execute("delete from widgets where id=?", (7,)).changes == 1
    assert gateway.allocate_id("widgets") == 8
    assert session.calls[0][1]["json"] == {
        "operation": "fetch_one",
        "sql": "select * from widgets where id=?",
        "params": [7],
    }


def test_d1_http_gateway_forwards_request_id():
    session = _FakeSession([_FakeResponse({"ok": True, "row": None})])
    gateway = D1HttpGateway(
        "http://d1.internal/query",
        session=session,
        request_id="request-123",
    )

    assert gateway.fetch_one("select 1") is None
    assert session.calls[0][1]["headers"] == {"X-Ordinarium-Request-Id": "request-123"}


def test_d1_http_gateway_rejects_bridge_errors_and_oversized_responses():
    failed = D1HttpGateway(
        "http://d1.internal/query",
        session=_FakeSession([_FakeResponse({"ok": False, "error": "bad"}, 400)]),
    )
    with pytest.raises(D1GatewayError, match="HTTP 400"):
        failed.fetch_all("select 1")

    oversized = D1HttpGateway(
        "http://d1.internal/query",
        max_response_bytes=2,
        session=_FakeSession([_FakeResponse({"ok": True, "rows": []})]),
    )
    with pytest.raises(D1GatewayError, match="size limit"):
        oversized.fetch_all("select 1")


def test_d1_gateway_errors_render_as_service_unavailable(app):
    class UnavailableGateway:
        def fetch_one(self, *_args, **_kwargs):
            raise D1GatewayError("D1 bridge returned HTTP 503.")

        def close(self):
            pass

    app.config["DATABASE_GATEWAY_FACTORY"] = UnavailableGateway
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = "1"
        session["_fresh"] = True

    response = client.get("/")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert b"database is temporarily unavailable" in response.data.lower()
