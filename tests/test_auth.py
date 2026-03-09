import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from ordinarium.db import get_db
from flask.testing import FlaskClient


def test_login_required_redirects_when_logged_out(client):
    response = client.get("/services")
    assert response.status_code == 302
    location = response.headers.get("Location", "")
    assert "/login" in location
    assert "next=" in location and "services" in location


def test_signup_creates_user_and_logs_in(app, client):
    response = client.post(
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
    with client.session_transaction() as session:
        assert session.get("_user_id")
    with app.app_context():
        db = get_db()
        user = db.execute(
            "select id, first_name from users where email=? limit 1",
            ("ada@example.com",),
        ).fetchone()
        assert user is not None
        assert user["first_name"] == "Ada"


def test_signup_redirect_shows_settings_flash(app, client):
    response = client.post(
        "/signup",
        data={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada2@example.com",
            "password": "strong-pass",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"<h2>Settings</h2>" in response.data
    assert (
        b"Your account is ready. Review your settings to match your needs, or keep the defaults."
        in response.data
    )


def test_signup_rejects_missing_csrf(app):
    app.config.update(WTF_CSRF_ENABLED=True)
    app.test_client_class = FlaskClient
    client = app.test_client()
    response = client.post(
        "/signup",
        data={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "password": "strong-pass",
        },
    )
    assert response.status_code == 400


def test_login_rejects_invalid_credentials(client, user_factory):
    user_factory(email="user@example.com", password="good-pass")
    response = client.post(
        "/login",
        data={"email": "user@example.com", "password": "bad-pass"},
    )
    assert response.status_code == 200
    assert b"Invalid email or password." in response.data


def test_authenticated_request_sets_last_accessed_when_empty(app, auth_client):
    client, user_id = auth_client

    with app.app_context():
        db = get_db()
        db.execute("update users set last_accessed_at=null where id=?", (user_id,))
        db.commit()

    response = client.get("/services")
    assert response.status_code == 200

    with app.app_context():
        db = get_db()
        row = db.execute(
            "select last_accessed_at from users where id=? limit 1",
            (user_id,),
        ).fetchone()
        assert row["last_accessed_at"] is not None


def test_authenticated_request_does_not_rewrite_recent_last_accessed(app, auth_client):
    client, user_id = auth_client
    recent_value = (datetime.utcnow() - timedelta(minutes=30)).isoformat()

    with app.app_context():
        db = get_db()
        db.execute(
            "update users set last_accessed_at=? where id=?",
            (recent_value, user_id),
        )
        db.commit()

    response = client.get("/services")
    assert response.status_code == 200

    with app.app_context():
        db = get_db()
        row = db.execute(
            "select last_accessed_at from users where id=? limit 1",
            (user_id,),
        ).fetchone()
        assert row["last_accessed_at"] == recent_value


def test_authenticated_request_rewrites_stale_last_accessed(app, auth_client):
    client, user_id = auth_client
    stale_value = (datetime.utcnow() - timedelta(hours=2)).isoformat()

    with app.app_context():
        db = get_db()
        db.execute(
            "update users set last_accessed_at=? where id=?",
            (stale_value, user_id),
        )
        db.commit()

    response = client.get("/services")
    assert response.status_code == 200

    with app.app_context():
        db = get_db()
        row = db.execute(
            "select last_accessed_at from users where id=? limit 1",
            (user_id,),
        ).fetchone()
        assert row["last_accessed_at"] != stale_value
        assert datetime.fromisoformat(row["last_accessed_at"]) > datetime.fromisoformat(
            stale_value
        )


def test_logged_out_request_does_not_write_last_accessed(app, client, user_factory):
    user_id = user_factory(email="logged-out@example.com")

    response = client.get("/login")
    assert response.status_code == 200

    with app.app_context():
        db = get_db()
        row = db.execute(
            "select last_accessed_at from users where id=? limit 1",
            (user_id,),
        ).fetchone()
        assert row["last_accessed_at"] is None


def test_last_access_migration_seeds_from_last_login(tmp_path):
    db_path = tmp_path / "migration-test.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            create table users (
              id integer primary key,
              email text not null,
              last_login_at text
            )
            """
        )
        conn.execute(
            "insert into users (id, email, last_login_at) values (?, ?, ?)",
            (1, "user@example.com", "2025-02-03T09:15:00"),
        )
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "migrations"
            / "035_add_user_last_access_tracking.sql"
        )
        conn.executescript(migration_path.read_text(encoding="utf-8"))
        row = conn.execute(
            "select last_login_at, last_accessed_at from users where id=1"
        ).fetchone()
        assert row[0] == "2025-02-03T09:15:00"
        assert row[1] == "2025-02-03T09:15:00"
    finally:
        conn.close()


def test_account_update_persists_changes(app, auth_client):
    client, user_id = auth_client
    response = client.post(
        "/account",
        data={
            "first_name": "Updated",
            "last_name": "Name",
            "email": "updated@example.com",
            "password": "new-password",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account")
    with app.app_context():
        db = get_db()
        user = db.execute(
            "select first_name, email, password_hash from users where id=? limit 1",
            (user_id,),
        ).fetchone()
        assert user["first_name"] == "Updated"
        assert user["email"] == "updated@example.com"
        assert user["password_hash"]
