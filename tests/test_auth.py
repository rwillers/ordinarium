from ordinarium.db import get_db


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
    assert response.headers["Location"].endswith("/services")
    with client.session_transaction() as session:
        assert session.get("user_id")
    with app.app_context():
        db = get_db()
        user = db.execute(
            "select id, first_name from users where email=? limit 1",
            ("ada@example.com",),
        ).fetchone()
        assert user is not None
        assert user["first_name"] == "Ada"


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
