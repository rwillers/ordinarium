import uuid

from ordinarium.db import get_db


def test_share_creates_link(auth_client, app, service_factory):
    client, user_id = auth_client
    service_factory(
        user_id=user_id,
        service_id=31,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.post("/service/31/share")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["share_url"]
    assert payload["share_uuid"]
    with app.app_context():
        db = get_db()
        share = db.execute(
            "select share_uuid from service_shares where service_id=? limit 1",
            (31,),
        ).fetchone()
        assert share is not None
        share_uuid = share["share_uuid"]
    assert payload["share_uuid"] == share_uuid


def test_share_denies_other_user(auth_client, service_factory, user_factory):
    client, _ = auth_client
    other_user_id = user_factory(email="other-share@example.com")
    service_factory(
        user_id=other_user_id,
        service_id=44,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.post("/service/44/share")
    assert response.status_code == 404
    assert b"Service not found" in response.data


def test_share_link_renders_without_login(client, app, service_factory, user_factory):
    user_id = user_factory()
    service_id = service_factory(
        user_id=user_id,
        service_id=51,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    share_uuid = str(uuid.uuid4())
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into service_shares (service_id, share_uuid) values (?, ?)",
            (service_id, share_uuid),
        )
        db.commit()
    response = client.get(f"/share/{share_uuid}")
    assert response.status_code == 200
    assert b"Holy Eucharist" in response.data


def test_share_link_missing_returns_404(client):
    response = client.get("/share/does-not-exist")
    assert response.status_code == 404
    assert b"Share link not found" in response.data


def test_share_reuses_existing_link(auth_client, app, service_factory):
    client, user_id = auth_client
    service_factory(
        user_id=user_id,
        service_id=63,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    first = client.post("/service/63/share").get_json()
    second = client.post("/service/63/share").get_json()
    assert first["share_uuid"] == second["share_uuid"]
    with app.app_context():
        db = get_db()
        shares = db.execute(
            "select count(*) as count from service_shares where service_id=?",
            (63,),
        ).fetchone()
        assert shares["count"] == 1
