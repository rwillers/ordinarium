from ordinarium.db import get_db


def test_integrations_requires_login(client):
    response = client.get("/integrations")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_integrations_shows_connect(app, auth_client):
    client, user_id = auth_client
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set feature_flags=? where id=?",
            ('{"pco_sync": true}', user_id),
        )
        db.commit()
    response = client.get("/integrations")
    assert response.status_code == 200
    assert b"Connect" in response.data


def test_integrations_shows_disconnect(app, auth_client):
    client, user_id = auth_client
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set feature_flags=? where id=?",
            ('{"pco_sync": true}', user_id),
        )
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.commit()
    response = client.get("/integrations")
    assert response.status_code == 200
    assert b"Disconnect" in response.data
