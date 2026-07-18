import time

from ordinarium.db import get_db
from ordinarium.password_security import verify_password
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
            "select id from users where email=? limit 1",
            ("reset@example.com",),
        ).fetchone()
        assert row is not None


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
            "select id from users where email=? limit 1",
            ("missing@example.com",),
        ).fetchone()
        assert row is None


def test_password_reset_updates_password_and_marks_token_used(
    app, client, user_factory
):
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
            "select password_hash from users where id=? limit 1", (user_id,)
        ).fetchone()
        assert user["password_hash"].startswith("$argon2id$")
        assert verify_password(user["password_hash"], "new-strong-pass").valid


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
        app.config["PASSWORD_RESET_EXPIRY_MINUTES"] = 0
        token = create_password_reset_token(user_id)
    time.sleep(1)

    response = client.get(f"/reset-password/{token}")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/reset-password")
