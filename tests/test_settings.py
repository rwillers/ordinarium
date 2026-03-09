from ordinarium.db import get_db


def _enable_pco_feature(app, user_id):
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set feature_flags=? where id=?",
            ('{"pco_sync": true}', user_id),
        )
        db.commit()


def test_settings_requires_login(client):
    response = client.get("/settings")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_settings_renders_saved_defaults(auth_client):
    client, _user_id = auth_client
    response = client.get("/settings")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "<h2>Settings</h2>" in body
    assert 'name="default_rite"' in body
    assert 'option value="Renewed Ancient Text" selected' in body
    assert 'option value="ESV" selected' in body
    assert 'name="default_service_time"' in body
    assert 'value="10:00"' in body


def test_settings_shows_integrations_section_when_pco_enabled(app, auth_client):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    response = client.get("/settings")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert 'id="settings-integrations"' in body
    assert 'name="default_service_time"' in body
    assert "Planning Center connection" in body


def test_header_shows_settings_and_hides_integrations_link(auth_client):
    client, _user_id = auth_client
    response = client.get("/services")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert ">Settings</a>" in body
    assert ">Integrations</a>" not in body


def test_settings_post_persists_valid_values(app, auth_client):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    response = client.post(
        "/settings",
        data={
            "default_rite": "Anglican Standard Text",
            "default_bible_translation": "NIV",
            "default_service_time": "08:30",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/settings")

    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            select default_rite, default_bible_translation, default_service_time
            from users
            where id=?
            """,
            (user_id,),
        ).fetchone()
        assert row["default_rite"] == "Anglican Standard Text"
        assert row["default_bible_translation"] == "NIV"
        assert row["default_service_time"] == "08:30"


def test_settings_post_rejects_invalid_rite(app, auth_client):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    response = client.post(
        "/settings",
        data={
            "default_rite": "Invalid Rite",
            "default_bible_translation": "NIV",
            "default_service_time": "08:30",
        },
    )
    assert response.status_code == 200
    assert b"Default rite is invalid." in response.data

    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            select default_rite, default_bible_translation, default_service_time
            from users
            where id=?
            """,
            (user_id,),
        ).fetchone()
        assert row["default_rite"] == "Renewed Ancient Text"
        assert row["default_bible_translation"] == "ESV"
        assert row["default_service_time"] == "10:00"


def test_settings_post_rejects_invalid_translation(app, auth_client):
    client, user_id = auth_client
    response = client.post(
        "/settings",
        data={
            "default_rite": "Renewed Ancient Text",
            "default_bible_translation": "MSG",
        },
    )
    assert response.status_code == 200
    assert b"Default Bible translation is invalid." in response.data

    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            select default_rite, default_bible_translation, default_service_time
            from users
            where id=?
            """,
            (user_id,),
        ).fetchone()
        assert row["default_rite"] == "Renewed Ancient Text"
        assert row["default_bible_translation"] == "ESV"
        assert row["default_service_time"] == "10:00"


def test_settings_post_rejects_invalid_service_time(app, auth_client):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    response = client.post(
        "/settings",
        data={
            "default_rite": "Renewed Ancient Text",
            "default_bible_translation": "ESV",
            "default_service_time": "25:61",
        },
    )
    assert response.status_code == 200
    assert b"Default service time must be a valid 24-hour time." in response.data

    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            select default_rite, default_bible_translation, default_service_time
            from users
            where id=?
            """,
            (user_id,),
        ).fetchone()
        assert row["default_rite"] == "Renewed Ancient Text"
        assert row["default_bible_translation"] == "ESV"
        assert row["default_service_time"] == "10:00"
