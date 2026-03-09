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
