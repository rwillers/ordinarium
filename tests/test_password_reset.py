import json
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash

from ordinarium.db import get_db
from ordinarium.routes import create_password_reset_token


def test_password_reset_request_creates_token(app, client, user_factory):
    user_id = user_factory(email="reset@example.com")
    response = client.post(
        "/reset-password",
        data={"email": "reset@example.com"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"If an account exists for that email" in response.data

    with app.app_context():
        db = get_db()
        row = db.execute(
            "select user_id, expires_at, used_at from password_reset_tokens where user_id=?",
            (user_id,),
        ).fetchone()
        assert row is not None
        assert row["used_at"] is None
        assert row["expires_at"] > datetime.now(timezone.utc).isoformat(timespec="seconds")


def test_password_reset_request_unknown_email_is_generic(app, client):
    response = client.post(
        "/reset-password",
        data={"email": "missing@example.com"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"If an account exists for that email" in response.data

    with app.app_context():
        db = get_db()
        row = db.execute(
            "select id from password_reset_tokens limit 1",
        ).fetchone()
        assert row is None


def test_password_reset_updates_password_and_marks_token_used(app, client, user_factory):
    user_id = user_factory(email="reset@example.com", password="old-pass")
    with app.app_context():
        token = create_password_reset_token(user_id)

    response = client.post(
        f"/reset-password/{token}",
        data={"password": "new-strong-pass"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    with app.app_context():
        db = get_db()
        user = db.execute(
            "select data from users where id=? limit 1", (user_id,)
        ).fetchone()
        payload = json.loads(user["data"])
        assert check_password_hash(payload["password_hash"], "new-strong-pass")

        token_row = db.execute(
            "select used_at from password_reset_tokens where user_id=? order by id desc limit 1",
            (user_id,),
        ).fetchone()
        assert token_row is not None
        assert token_row["used_at"] is not None


def test_password_reset_rejects_reused_token(app, client, user_factory):
    user_id = user_factory(email="reset@example.com")
    with app.app_context():
        token = create_password_reset_token(user_id)

    client.post(
        f"/reset-password/{token}",
        data={"password": "new-strong-pass"},
    )
    response = client.post(
        f"/reset-password/{token}",
        data={"password": "another-pass"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/reset-password")


def test_password_reset_rejects_expired_token(app, client, user_factory):
    user_id = user_factory(email="reset@example.com")
    with app.app_context():
        token = create_password_reset_token(user_id)
        db = get_db()
        expired_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
        db.execute(
            "update password_reset_tokens set expires_at=? where user_id=?",
            (expired_at, user_id),
        )
        db.commit()

    response = client.get(f"/reset-password/{token}")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/reset-password")
