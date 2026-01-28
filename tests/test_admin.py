from ordinarium.db import get_db


def test_admin_requires_login(client):
    response = client.get("/admin")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_denies_without_flag(auth_client):
    client, _ = auth_client
    response = client.get("/admin")
    assert response.status_code == 404


def test_admin_allows_with_flag(app, auth_client):
    client, user_id = auth_client
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set feature_flags=? where id=?",
            ('{"admin": true}', user_id),
        )
        db.commit()
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"Users" in response.data
