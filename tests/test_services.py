import json

from ordinarium.db import get_db


def test_services_new_redirects_to_next_id(auth_client, service_factory):
    client, user_id = auth_client
    service_factory(user_id=user_id, service_id=10)
    response = client.get("/services/new")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/service/11")


def test_service_missing_id_returns_error(auth_client):
    client, _ = auth_client
    response = client.get("/service")
    assert response.status_code == 400
    assert b"Service ID required" in response.data


def test_service_denies_other_user(auth_client, service_factory, user_factory):
    client, _ = auth_client
    other_user_id = user_factory(email="other@example.com")
    service_factory(user_id=other_user_id, service_id=22, service_date="2026-01-04")
    response = client.get("/service/22")
    assert response.status_code == 404
    assert b"Service not found" in response.data


def test_persist_service_requires_date(auth_client):
    client, _ = auth_client
    response = client.post(
        "/persist/service",
        data={"service_id": "5", "rite": "Renewed Ancient Text", "ids": "68,69"},
    )
    assert response.status_code == 400
    assert b"Service date is required." in response.data


def test_persist_service_saves_and_generates_text(app, auth_client):
    client, user_id = auth_client
    response = client.post(
        "/persist/service",
        data={
            "service_id": "7",
            "rite": "Renewed Ancient Text",
            "service_date": "2026-01-04",
            "ids": "68,69",
            "disabled": "69",
            "action": "generate",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/text/7")
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select data from services where id=? limit 1", (7,)
        ).fetchone()
        payload = json.loads(service["data"])
        assert payload["user_id"] == user_id
        assert payload["service_date"] == "2026-01-04"


def test_persist_service_defaults_invalid_id_to_one(app, auth_client):
    client, user_id = auth_client
    with app.app_context():
        db = get_db()
        db.execute("delete from services")
        db.commit()
    response = client.post(
        "/persist/service",
        data={
            "service_id": "not-a-number",
            "rite": "Renewed Ancient Text",
            "service_date": "2026-01-04",
            "ids": "68,69",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/service/1")
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select data from services where id=? limit 1", (1,)
        ).fetchone()
        payload = json.loads(service["data"])
        assert payload["user_id"] == user_id


def test_persist_service_normalizes_observance_handle(app, auth_client):
    client, user_id = auth_client
    response = client.post(
        "/persist/service",
        data={
            "service_id": "12",
            "rite": "Renewed Ancient Text",
            "service_date": "2024-12-01",
            "observance_handle": "bad-handle",
            "ids": "68,69",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select data from services where id=? limit 1", (12,)
        ).fetchone()
        payload = json.loads(service["data"])
        assert payload["user_id"] == user_id
        assert payload["observance_handle"] == "AdventI"
        assert payload["title"] == "The First Sunday in Advent"


def test_text_missing_service_returns_error(auth_client):
    client, _ = auth_client
    response = client.get("/text/999")
    assert response.status_code == 400
    assert b"Service ID required" in response.data


def test_text_renders_for_saved_service(auth_client, service_factory):
    client, user_id = auth_client
    service_factory(
        user_id=user_id,
        service_id=14,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.get("/text/14")
    assert response.status_code == 200
    assert b"Holy Eucharist" in response.data
