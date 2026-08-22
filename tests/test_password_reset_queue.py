import base64
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

import ordinarium.password_reset_routes as password_reset_routes
from ordinarium.db import get_db
from ordinarium.password_reset_email_processor import (
    dead_letter_password_reset_message,
    process_password_reset_message,
)
from ordinarium.password_reset_store import (
    PasswordResetEnvelopeError,
    create_queued_password_reset,
    decrypt_delivery_token,
    get_queued_password_reset_record,
)
from ordinarium.password_security import verify_password
from ordinarium.queue_publisher import QueuePublicationUnavailable


DELIVERY_KEY = base64.urlsafe_b64encode(b"r" * 32).decode("ascii")


class ProviderResponse:
    def __init__(self, status_code=202, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


def _enable_queued_resets(app):
    app.config.update(
        QUEUE_SERVICE_URL="http://queue.internal",
        PASSWORD_RESET_DELIVERY_KEY=DELIVERY_KEY,
    )


def _enable_email_delivery(app, transport):
    app.config.update(
        PASSWORD_RESET_DELIVERY_KEY=DELIVERY_KEY,
        DEPLOYMENT_ENV="staging",
        APP_ORIGIN="https://staging.ordinarium.com",
        SIDE_EFFECTS_HOSTNAME="staging.ordinarium.com",
        EXTERNAL_SIDE_EFFECTS_ENABLED=True,
        MAILERSEND_API_TOKEN="provider-secret",
        MAILERSEND_FROM_EMAIL="no-reply@example.com",
        MAILERSEND_FROM_NAME="Ordinarium",
        MAILERSEND_TRANSPORT=transport,
    )


def _create_reset(app, user_id):
    with app.app_context():
        reset = create_queued_password_reset(user_id)
        row = (
            get_db()
            .execute(
                "select * from password_reset_requests where id=?", (reset["reset_id"],)
            )
            .fetchone()
        )
        return reset, dict(row)


def test_queued_web_request_publishes_only_opaque_id_and_persists_no_plaintext(
    app, client, user_factory, monkeypatch
):
    user_factory(email="queued@example.com")
    _enable_queued_resets(app)
    messages = []
    monkeypatch.setattr(
        password_reset_routes,
        "publish_password_reset",
        lambda **payload: messages.append(payload),
    )

    response = client.post("/reset-password", data={"email": "queued@example.com"})

    assert response.status_code == 302
    assert list(messages[0]) == ["reset_id"]
    with app.app_context():
        row = (
            get_db()
            .execute(
                "select * from password_reset_requests where id=?",
                (messages[0]["reset_id"],),
            )
            .fetchone()
        )
        assert len(row["token_hash"]) == 64
        token = decrypt_delivery_token(row["id"], row["delivery_token_envelope"])
        assert token not in row["delivery_token_envelope"]
        assert token.split(".")[2] not in row["delivery_token_envelope"]


def test_total_publication_failure_remains_recoverable_and_does_not_log_token(
    app, client, user_factory, monkeypatch, caplog
):
    user_factory(email="queued@example.com")
    _enable_queued_resets(app)
    monkeypatch.setattr(
        password_reset_routes,
        "publish_password_reset",
        lambda **_payload: (_ for _ in ()).throw(
            QueuePublicationUnavailable("queue unavailable")
        ),
    )
    with caplog.at_level(logging.WARNING):
        response = client.post("/reset-password", data={"email": "queued@example.com"})

    assert response.status_code == 302
    with app.app_context():
        row = (
            get_db()
            .execute(
                "select * from password_reset_requests order by created_at desc limit 1"
            )
            .fetchone()
        )
        assert row["delivery_status"] == "queued"
        token = decrypt_delivery_token(row["id"], row["delivery_token_envelope"])
    assert token not in caplog.text


def test_queued_reset_is_atomic_one_use_and_clears_delivery_material(
    app, client, user_factory
):
    user_id = user_factory(email="queued@example.com", password="old-password")
    _enable_queued_resets(app)
    reset, _row = _create_reset(app, user_id)

    first = client.post(
        f"/reset-password/{reset['token']}", data={"password": "new-password"}
    )
    second = client.post(
        f"/reset-password/{reset['token']}", data={"password": "other-password"}
    )

    assert first.headers["Location"].endswith("/login")
    assert second.headers["Location"].endswith("/reset-password")
    with app.app_context():
        row = (
            get_db()
            .execute(
                "select * from password_reset_requests where id=?", (reset["reset_id"],)
            )
            .fetchone()
        )
        user = (
            get_db()
            .execute("select password_hash from users where id=?", (user_id,))
            .fetchone()
        )
        assert row["used_at"] is not None
        assert row["delivery_token_envelope"] is None
        assert verify_password(user["password_hash"], "new-password").valid
        assert not verify_password(user["password_hash"], "other-password").valid


def test_queued_reset_rejects_tamper_expiry_and_deleted_user(app, user_factory):
    user_id = user_factory(email="queued@example.com")
    _enable_queued_resets(app)
    reset, _row = _create_reset(app, user_id)

    with app.app_context():
        assert get_queued_password_reset_record(reset["token"] + "x") is None
        expired_now = datetime.now(timezone.utc) + timedelta(hours=2)
        assert get_queued_password_reset_record(reset["token"], now=expired_now) is None
        get_db().execute(
            "update users set deleted_at=CURRENT_TIMESTAMP where id=?", (user_id,)
        )
        get_db().commit()
        assert get_queued_password_reset_record(reset["token"]) is None


def test_delivery_envelope_authenticates_ciphertext(app, user_factory):
    user_id = user_factory(email="queued@example.com")
    _enable_queued_resets(app)
    reset, row = _create_reset(app, user_id)
    envelope = row["delivery_token_envelope"]
    parts = envelope.split(":")
    padding = "=" * (-len(parts[-1]) % 4)
    ciphertext = bytearray(base64.urlsafe_b64decode(parts[-1] + padding))
    ciphertext[0] ^= 1
    parts[-1] = base64.urlsafe_b64encode(ciphertext).decode("ascii").rstrip("=")
    tampered = ":".join(parts)

    with app.app_context(), pytest.raises(PasswordResetEnvelopeError):
        decrypt_delivery_token(reset["reset_id"], tampered)


def test_email_delivery_is_idempotent_and_persists_provider_id(app, user_factory):
    user_id = user_factory(email="queued@example.com")
    calls = []

    def transport(*args, **kwargs):
        calls.append((args, kwargs))
        return ProviderResponse(202, {"x-message-id": "message-123"})

    _enable_email_delivery(app, transport)
    reset, _row = _create_reset(app, user_id)
    with app.app_context():
        first = process_password_reset_message({"reset_id": reset["reset_id"]})
        duplicate = process_password_reset_message({"reset_id": reset["reset_id"]})
        row = (
            get_db()
            .execute(
                "select * from password_reset_requests where id=?", (reset["reset_id"],)
            )
            .fetchone()
        )

    assert first[1] == 200
    assert duplicate[1] == 200
    assert len(calls) == 1
    assert row["delivery_status"] == "sent"
    assert row["delivery_provider_id"] == "message-123"
    assert row["delivery_token_envelope"] is None


@pytest.mark.parametrize(
    ("status_code", "headers", "expected_status"),
    [
        (202, {}, "suppressed"),
        (200, {"x-message-id": "accepted-123"}, "accepted"),
    ],
)
def test_email_success_without_202_provider_id_uses_safe_terminal_state(
    app, user_factory, status_code, headers, expected_status
):
    user_id = user_factory(email="queued@example.com")
    _enable_email_delivery(
        app, lambda *_args, **_kwargs: ProviderResponse(status_code, headers)
    )
    reset, _row = _create_reset(app, user_id)

    with app.app_context():
        body, response_status = process_password_reset_message(
            {"reset_id": reset["reset_id"]}
        )
        row = (
            get_db()
            .execute(
                "select * from password_reset_requests where id=?", (reset["reset_id"],)
            )
            .fetchone()
        )

    assert response_status == 200
    assert body["category"] == expected_status
    assert row["delivery_status"] == expected_status
    assert row["delivery_provider_id"] == headers.get("x-message-id")
    assert row["delivery_token_envelope"] is None


@pytest.mark.parametrize(
    ("provider_result", "category"),
    [
        (requests.ConnectionError("offline"), "network"),
        (ProviderResponse(429, {"Retry-After": "17"}), "provider_rate_limit"),
        (ProviderResponse(503), "provider_unavailable"),
    ],
)
def test_email_transient_failures_persist_retry(
    app, user_factory, provider_result, category
):
    user_id = user_factory(email="queued@example.com")

    def transport(*_args, **_kwargs):
        if isinstance(provider_result, Exception):
            raise provider_result
        return provider_result

    _enable_email_delivery(app, transport)
    reset, _row = _create_reset(app, user_id)
    with app.app_context():
        body, status = process_password_reset_message({"reset_id": reset["reset_id"]})
        row = (
            get_db()
            .execute(
                "select * from password_reset_requests where id=?", (reset["reset_id"],)
            )
            .fetchone()
        )

    assert status == 503
    assert body["category"] == category
    assert row["delivery_status"] == "retry"
    assert row["delivery_last_error"] == category
    assert row["delivery_token_envelope"] is not None


@pytest.mark.parametrize(
    ("status_code", "category"),
    [(400, "provider_rejected_400"), (401, "provider_auth")],
)
def test_email_provider_terminal_failures_clear_envelope(
    app, user_factory, status_code, category
):
    user_id = user_factory(email="queued@example.com")
    _enable_email_delivery(app, lambda *_args, **_kwargs: ProviderResponse(status_code))
    reset, _row = _create_reset(app, user_id)
    with app.app_context():
        body, status = process_password_reset_message({"reset_id": reset["reset_id"]})
        row = (
            get_db()
            .execute(
                "select * from password_reset_requests where id=?", (reset["reset_id"],)
            )
            .fetchone()
        )

    assert status == 200
    assert body["category"] == category
    assert row["delivery_status"] == "failed"
    assert row["delivery_token_envelope"] is None


def test_expired_sending_lease_restarts_and_dlq_terminalizes(app, user_factory):
    user_id = user_factory(email="queued@example.com")
    calls = []
    _enable_email_delivery(
        app,
        lambda *_args, **_kwargs: (
            calls.append(True) or ProviderResponse(202, {"x-message-id": "restart"})
        ),
    )
    reset, _row = _create_reset(app, user_id)
    with app.app_context():
        get_db().execute(
            """
            update password_reset_requests
            set delivery_status='sending', delivery_claim_token='dead-process',
                delivery_claim_expires_at=1
            where id=?
            """,
            (reset["reset_id"],),
        )
        get_db().commit()
        body, status = process_password_reset_message({"reset_id": reset["reset_id"]})
    assert status == 200
    assert body["category"] == "sent"
    assert calls == [True]

    second, _row = _create_reset(app, user_id)
    with app.app_context():
        body, status = dead_letter_password_reset_message(
            {"reset_id": second["reset_id"]}
        )
        row = (
            get_db()
            .execute(
                "select * from password_reset_requests where id=?",
                (second["reset_id"],),
            )
            .fetchone()
        )
    assert status == 200
    assert body["category"] == "retry_exhausted"
    assert row["delivery_status"] == "failed"
    assert row["delivery_last_error"] == "retry_exhausted"
    assert row["delivery_token_envelope"] is None


def test_password_reset_schema_matches_sqlite_forward_and_d1_migrations(app):
    root = Path(__file__).parents[1]
    with sqlite3.connect(app.config["DATABASE"]) as canonical:
        canonical_columns = {
            row[1]
            for row in canonical.execute("pragma table_info(password_reset_requests)")
        }
        canonical_indexes = {
            row[1]
            for row in canonical.execute("pragma index_list(password_reset_requests)")
        }
        canonical_cleanup_index_sql = canonical.execute(
            "select sql from sqlite_schema where type='index' and name=?",
            ("idx_password_reset_expiry_cleanup",),
        ).fetchone()[0]

    with sqlite3.connect(":memory:") as forward:
        forward.execute("create table users (id integer primary key)")
        forward.executescript(
            (
                root / "scripts/migrations/042_add_password_reset_requests.sql"
            ).read_text()
        )
        forward.executescript(
            (
                root / "scripts/migrations/044_add_password_reset_cleanup_index.sql"
            ).read_text()
        )
        forward_columns = {
            row[1]
            for row in forward.execute("pragma table_info(password_reset_requests)")
        }
        forward_indexes = {
            row[1]
            for row in forward.execute("pragma index_list(password_reset_requests)")
        }
        forward_cleanup_index_sql = forward.execute(
            "select sql from sqlite_schema where type='index' and name=?",
            ("idx_password_reset_expiry_cleanup",),
        ).fetchone()[0]

    with sqlite3.connect(":memory:") as d1:
        d1.executescript(
            """
            create table users (id integer primary key);
            create table services (id integer primary key);
            create table service_custom_elements (id integer primary key);
            create table pco_connections (user_id integer primary key);
            create table pco_batch_sync_jobs (id text primary key);
            """
        )
        d1.executescript(
            (root / "migrations/d1/0004_operational_state.sql").read_text()
        )
        d1.executescript(
            (root / "migrations/d1/0007_password_reset_cleanup_index.sql").read_text()
        )
        d1_columns = {
            row[1] for row in d1.execute("pragma table_info(password_reset_requests)")
        }
        d1_indexes = {
            row[1] for row in d1.execute("pragma index_list(password_reset_requests)")
        }
        d1_cleanup_index_sql = d1.execute(
            "select sql from sqlite_schema where type='index' and name=?",
            ("idx_password_reset_expiry_cleanup",),
        ).fetchone()[0]

    assert canonical_columns == forward_columns == d1_columns
    assert "idx_password_reset_expiry_cleanup" in canonical_indexes
    assert "idx_password_reset_expiry_cleanup" in forward_indexes
    assert "idx_password_reset_expiry_cleanup" in d1_indexes
    normalized_cleanup_indexes = {
        " ".join(value.lower().split())
        for value in (
            canonical_cleanup_index_sql,
            forward_cleanup_index_sql,
            d1_cleanup_index_sql,
        )
    }
    assert len(normalized_cleanup_indexes) == 1
    cleanup_index_sql = next(iter(normalized_cleanup_indexes))
    assert "(delivery_status, expires_at, id)" in cleanup_index_sql
    assert "where used_at is null" in cleanup_index_sql
    assert "delivery_status in ('queued','sending','retry')" in cleanup_index_sql
