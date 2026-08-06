import sqlite3

import pytest
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

from ordinarium import create_app
from ordinarium.db import get_db, init_db
from ordinarium.infrastructure import SQLiteGateway
from ordinarium.password_security import verify_password
from ordinarium.pco_batch_jobs import create_pco_batch_sync_job, get_pco_batch_sync_job
from ordinarium.pco_store import get_pco_connection, upsert_pco_connection
from ordinarium.service_store import blank_service_payload, create_service_record
from ordinarium.user_store import create_user


@pytest.fixture()
def gateway_app(tmp_path):
    gateway_database = tmp_path / "gateway.db"
    direct_database = tmp_path / "direct-access-must-not-be-used.db"
    app = create_app()
    app.config.update(
        TESTING=True,
        DATABASE=str(gateway_database),
        SECRET_KEY="test",
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
        PCO_TOKEN_ENCRYPTION_KEYS={
            "v1": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
        },
    )
    with app.app_context():
        init_db()

    def gateway_factory():
        connection = sqlite3.connect(gateway_database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return SQLiteGateway(connection)

    app.config.update(
        DATABASE=str(direct_database),
        DATABASE_GATEWAY_BACKEND="d1",
        DATABASE_GATEWAY_FACTORY=gateway_factory,
    )
    app.test_client_class = FlaskClient
    return app


@pytest.fixture()
def gateway_client(gateway_app):
    return gateway_app.test_client()


def test_account_routes_use_gateway_backend(gateway_app, gateway_client):
    with gateway_app.app_context():
        user = create_user(
            "Legacy",
            "User",
            "legacy@example.com",
            generate_password_hash("legacy-pass", method="scrypt"),
            "2026-07-18T12:00:00",
        )

    response = gateway_client.post(
        "/login",
        data={"email": "legacy@example.com", "password": "legacy-pass"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/services")

    response = gateway_client.post(
        "/account",
        data={
            "first_name": "Updated",
            "last_name": "User",
            "email": "updated@example.com",
            "password": "updated-pass",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account")

    with gateway_app.app_context():
        from ordinarium.user_store import get_user_by_id

        updated = get_user_by_id(user["id"])
    assert updated["first_name"] == "Updated"
    assert updated["email"] == "updated@example.com"
    assert verify_password(updated["password_hash"], "updated-pass").valid
    assert not direct_database_has_tables(gateway_app.config["DATABASE"])


def test_signup_and_settings_use_gateway_backend(gateway_app, gateway_client):
    response = gateway_client.post(
        "/signup",
        data={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "password": "strong-pass",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/settings")

    response = gateway_client.post(
        "/settings",
        data={
            "default_rite": "Anglican Standard Text",
            "default_bible_translation": "NIV",
            "greeting_response_form": "also_with_you",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/settings")

    with gateway_app.app_context():
        from ordinarium.user_store import get_user_by_email

        user = get_user_by_email("ada@example.com")
    assert user["default_rite"] == "Anglican Standard Text"
    assert user["default_bible_translation"] == "NIV"
    assert user["greeting_response_form"] == "also_with_you"
    assert not direct_database_has_tables(gateway_app.config["DATABASE"])


def direct_database_has_tables(path):
    connection = sqlite3.connect(path)
    try:
        return bool(
            connection.execute(
                "select 1 from sqlite_master where type='table' limit 1"
            ).fetchone()
        )
    finally:
        connection.close()


def test_service_routes_use_gateway_backend(gateway_app, gateway_client):
    user = create_gateway_user(gateway_app)
    authenticate(gateway_client, user["id"])

    response = gateway_client.post(
        "/services",
        data={
            "mode": "defaults",
            "add_mode": "single",
            "rite": "Renewed Ancient Text",
            "service_date": "2099-01-04",
        },
    )
    assert response.status_code == 302
    service_url = response.headers["Location"]
    assert "/service/" in service_url

    assert gateway_client.get("/services").status_code == 200
    assert gateway_client.get(service_url).status_code == 200
    assert not direct_database_has_tables(gateway_app.config["DATABASE"])


def test_service_mutations_templates_and_sharing_use_gateway_backend(
    gateway_app, gateway_client
):
    user = create_gateway_user(gateway_app, email="planner@example.com")
    with gateway_app.app_context():
        from ordinarium.db import get_database_gateway

        payload = blank_service_payload(user["id"])
        payload.update(service_date="2099-01-04", title="Gateway service")
        service_id = create_service_record(get_database_gateway(), payload)
    authenticate(gateway_client, user["id"])

    response = gateway_client.patch(
        f"/service/{service_id}",
        data={
            "autosave": "1",
            "rite": "Renewed Ancient Text",
            "service_date": "2099-01-04",
            "ids": "",
            "disabled": "",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    response = gateway_client.post(
        f"/service/{service_id}/custom-element",
        data={"title": "Prayer", "text": "Custom text", "autosave": "1"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    assert response.get_json()["token"].startswith("custom:")

    response = gateway_client.post(f"/service/{service_id}/share")
    assert response.status_code == 200
    assert response.get_json()["share_uuid"]

    response = gateway_client.post(
        "/templates",
        data={"title": "Gateway template", "text": "Template text"},
    )
    assert response.status_code == 302
    assert gateway_client.get("/templates").status_code == 200
    assert not direct_database_has_tables(gateway_app.config["DATABASE"])


def test_administration_routes_use_gateway_backend(gateway_app, gateway_client):
    admin = create_gateway_user(gateway_app, email="admin@example.com")
    target = create_gateway_user(gateway_app, email="target@example.com")
    with gateway_app.app_context():
        from ordinarium.db import get_database_gateway

        get_database_gateway().execute(
            "update users set feature_flags=? where id=?",
            ('{"admin": true}', admin["id"]),
        )
    authenticate(gateway_client, admin["id"])

    assert gateway_client.get("/admin").status_code == 200
    response = gateway_client.post(
        f"/admin/users/{target['id']}",
        data={
            "first_name": "Managed",
            "last_name": "User",
            "email": "managed@example.com",
            "flag_pco_sync": "1",
        },
    )
    assert response.status_code == 302

    response = gateway_client.post(f"/admin/users/{target['id']}/delete")
    assert response.status_code == 302
    with gateway_app.app_context():
        from ordinarium.db import get_database_gateway

        deleted = get_database_gateway().fetch_one(
            "select email, deleted_at from users where id=?",
            (target["id"],),
        )
    assert deleted["email"] == "managed@example.com"
    assert deleted["deleted_at"]
    assert not direct_database_has_tables(gateway_app.config["DATABASE"])


def test_pco_persistence_uses_gateway_and_encrypted_envelopes(
    gateway_app, gateway_client
):
    user = create_gateway_user(gateway_app, email="pco@example.com")
    with gateway_app.app_context():
        from ordinarium.db import get_database_gateway

        gateway = get_database_gateway()
        gateway.execute(
            "update users set feature_flags=? where id=?",
            ('{"pco_sync": true}', user["id"]),
        )
        upsert_pco_connection(
            user["id"],
            "access-secret",
            "refresh-secret",
            "bearer",
            "services",
        )
        stored = gateway.fetch_one(
            "select access_token, refresh_token from pco_connections where user_id=?",
            (user["id"],),
        )
        connection = get_pco_connection(user["id"])
        job_id = create_pco_batch_sync_job(user["id"], {"service_ids": [1]})
        job = get_pco_batch_sync_job(job_id, user["id"])

    assert stored["access_token"].startswith("aesgcm:v1:")
    assert stored["refresh_token"].startswith("aesgcm:v1:")
    assert connection["access_token"] == "access-secret"
    assert connection["refresh_token"] == "refresh-secret"
    assert job["status"] == "queued"

    authenticate(gateway_client, user["id"])
    response = gateway_client.get("/settings/connections")
    assert response.status_code == 200
    assert b"Disconnect" in response.data
    assert not direct_database_has_tables(gateway_app.config["DATABASE"])


def create_gateway_user(gateway_app, email="gateway@example.com"):
    with gateway_app.app_context():
        return create_user(
            "Gateway",
            "User",
            email,
            generate_password_hash("gateway-pass", method="scrypt"),
            "2026-07-18T12:00:00",
        )


def authenticate(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True
