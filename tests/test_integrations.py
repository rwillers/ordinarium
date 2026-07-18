from ordinarium.db import get_db
from ordinarium.pco_client import PcoToken
from ordinarium.pco_store import get_pco_connection


def _enable_pco_feature(app, user_id):
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set feature_flags=? where id=?",
            ('{"pco_sync": true}', user_id),
        )
        db.commit()


def test_integrations_requires_login(client):
    response = client.get("/integrations")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_integrations_redirects_to_settings_anchor(app, auth_client):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    response = client.get("/integrations")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/settings#settings-integrations")


def test_settings_shows_connect_for_pco(app, auth_client):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    response = client.get("/settings")
    assert response.status_code == 200
    assert b"Connect" in response.data


def test_settings_shows_disconnect_for_pco(app, auth_client):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.commit()
    response = client.get("/settings")
    assert response.status_code == 200
    assert b"Disconnect" in response.data


def test_settings_shows_connected_org_name(app, auth_client):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            insert into pco_connections (
              user_id,
              access_token,
              pco_account_name
            ) values (?, ?, ?)
            """,
            (user_id, "token", "St. Mark Church"),
        )
        db.commit()
    response = client.get("/settings")
    assert response.status_code == 200
    assert b"Connected to St. Mark Church." in response.data


def test_pco_disconnect_clears_only_upcoming_links_for_user(
    app, auth_client, user_factory, service_factory
):
    client, user_id = auth_client
    other_user_id = user_factory(email="other@example.com")
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set feature_flags=? where id=?",
            ('{"pco_sync": true}', user_id),
        )
        db.execute(
            "update users set feature_flags=? where id=?",
            ('{"pco_sync": true}', other_user_id),
        )
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (other_user_id, "other-token"),
        )
        db.commit()

    upcoming_service_id = service_factory(
        user_id=user_id,
        service_id=101,
        service_date="2099-01-01",
    )
    past_service_id = service_factory(
        user_id=user_id,
        service_id=102,
        service_date="2000-01-01",
    )
    other_upcoming_service_id = service_factory(
        user_id=other_user_id,
        service_id=201,
        service_date="2099-01-01",
    )

    with app.app_context():
        db = get_db()
        db.execute(
            """
            insert into service_pco_links (
              service_id,
              pco_service_type_id,
              pco_plan_id
            ) values (?, ?, ?)
            """,
            (upcoming_service_id, "type-upcoming", "plan-upcoming"),
        )
        db.execute(
            """
            insert into service_pco_links (
              service_id,
              pco_service_type_id,
              pco_plan_id
            ) values (?, ?, ?)
            """,
            (past_service_id, "type-past", "plan-past"),
        )
        db.execute(
            """
            insert into service_pco_links (
              service_id,
              pco_service_type_id,
              pco_plan_id
            ) values (?, ?, ?)
            """,
            (other_upcoming_service_id, "type-other", "plan-other"),
        )
        db.commit()

    response = client.post("/integrations/pco/disconnect")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/settings#settings-integrations")

    with app.app_context():
        db = get_db()
        connection = db.execute(
            "select user_id from pco_connections where user_id=?",
            (user_id,),
        ).fetchone()
        assert connection is None
        other_connection = db.execute(
            "select user_id from pco_connections where user_id=?",
            (other_user_id,),
        ).fetchone()
        assert other_connection is not None

        user_links = db.execute(
            """
            select service_id
            from service_pco_links
            where service_id in (?, ?)
            order by service_id
            """,
            (upcoming_service_id, past_service_id),
        ).fetchall()
        assert [row["service_id"] for row in user_links] == [past_service_id]

        other_link = db.execute(
            "select service_id from service_pco_links where service_id=?",
            (other_upcoming_service_id,),
        ).fetchone()
        assert other_link is not None


def test_pco_callback_stores_org_name(app, auth_client, monkeypatch):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    app.config.update(
        PCO_CLIENT_ID="client-id",
        PCO_CLIENT_SECRET="client-secret",
    )

    with client.session_transaction() as session:
        session["pco_oauth_state"] = "state-token"

    monkeypatch.setattr(
        "ordinarium.integrations_routes.exchange_code_for_token",
        lambda *_args, **_kwargs: PcoToken(
            access_token="fresh-token",
            refresh_token="fresh-refresh",
            token_type="bearer",
            scope="services",
        ),
    )
    monkeypatch.setattr(
        "ordinarium.integrations_routes.fetch_services_organization_name",
        lambda *_args, **_kwargs: "St. Mark Church",
    )

    response = client.get("/integrations/pco/callback?state=state-token&code=code-123")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/settings#settings-integrations")

    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            select access_token, refresh_token, token_type, scope, pco_account_name
            from pco_connections
            where user_id=?
            """,
            (user_id,),
        ).fetchone()
        assert row is not None
        assert row["access_token"].startswith("aesgcm:v1:")
        assert row["refresh_token"].startswith("aesgcm:v1:")
        assert row["token_type"] == "bearer"
        assert row["scope"] == "services"
        assert row["pco_account_name"] == "St. Mark Church"
        connection = get_pco_connection(user_id)
        assert connection["access_token"] == "fresh-token"
        assert connection["refresh_token"] == "fresh-refresh"


def test_pco_callback_allows_org_lookup_failure(app, auth_client, monkeypatch):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    app.config.update(
        PCO_CLIENT_ID="client-id",
        PCO_CLIENT_SECRET="client-secret",
    )

    with client.session_transaction() as session:
        session["pco_oauth_state"] = "state-token"

    monkeypatch.setattr(
        "ordinarium.integrations_routes.exchange_code_for_token",
        lambda *_args, **_kwargs: PcoToken(access_token="fresh-token"),
    )

    def _raise_lookup_error(*_args, **_kwargs):
        raise RuntimeError("lookup failed")

    monkeypatch.setattr(
        "ordinarium.integrations_routes.fetch_services_organization_name",
        _raise_lookup_error,
    )

    response = client.get("/integrations/pco/callback?state=state-token&code=code-123")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/settings#settings-integrations")

    with app.app_context():
        db = get_db()
        row = db.execute(
            "select pco_account_name from pco_connections where user_id=?",
            (user_id,),
        ).fetchone()
        assert row is not None
        assert row["pco_account_name"] is None
