from datetime import date, timedelta

from ordinarium.db import get_db
from ordinarium.liturgical_calendar import resolve_season


def _enable_pco_feature(app, user_id):
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set feature_flags=? where id=?",
            ('{"pco_sync": true}', user_id),
        )
        db.commit()


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_season_endpoint_handles_blank(client):
    response = client.get("/season")
    assert response.status_code == 200
    assert response.get_json() == {"season": None}


def test_season_endpoint_resolves_date(client):
    target = date(2026, 1, 4)
    response = client.get(f"/season?date={target.isoformat()}")
    assert response.status_code == 200
    assert response.get_json() == {"season": resolve_season(target)}


def test_observance_endpoint_handles_invalid_date(client):
    response = client.get("/observance?date=invalid")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["title"] is None
    assert payload["handle"] is None
    assert payload["options"] == []
    assert payload["lesson_defaults"] == {}


def test_observance_endpoint_returns_options_for_date(client):
    response = client.get("/observance?date=2024-12-01")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["handle"] == "AdventI"
    assert payload["title"] == "The First Sunday in Advent"
    assert payload["season"] == "Advent"
    assert payload["options"]
    lesson_defaults = payload["lesson_defaults"]
    assert isinstance(lesson_defaults, dict)
    assert set(lesson_defaults.keys()) == {
        "lesson_1",
        "psalm",
        "lesson_2",
        "gospel",
    }


def test_propers_search_results_handles_blank_date(client):
    response = client.get("/propers-search/results")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["date"] is None
    assert payload["observances"] == []


def test_propers_search_results_handles_invalid_date(client):
    response = client.get("/propers-search/results?date=invalid")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["date"] == "invalid"
    assert payload["observances"] == []


def test_home_page_shows_up_to_three_upcoming_services(auth_client, service_factory):
    client, user_id = auth_client
    today = date.today()
    for index in range(4):
        service_factory(
            user_id=user_id,
            service_id=1001 + index,
            title=f"Upcoming {index + 1}",
            service_date=(today + timedelta(days=index + 1)).isoformat(),
        )
    service_factory(
        user_id=user_id,
        service_id=1010,
        title="Past service",
        service_date=(today - timedelta(days=1)).isoformat(),
    )

    response = client.get("/")
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    assert body.count('class="home-service-actions"') == 3
    assert "/service/1001/view" in body
    assert "/service/1001/export.pdf" in body
    assert "/service/1001/export.docx" in body
    assert "/service/1004/view" not in body
    assert "/service/1010/view" not in body
    assert "Share service link" not in body
    assert "home-service-view-all" in body


def test_home_page_shows_pco_status_for_upcoming_services(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    today = date.today()
    first_id = service_factory(
        user_id=user_id,
        service_id=1101,
        title="Synced service",
        service_date=(today + timedelta(days=1)).isoformat(),
    )
    second_id = service_factory(
        user_id=user_id,
        service_id=1102,
        title="Failed service",
        service_date=(today + timedelta(days=2)).isoformat(),
    )
    third_id = service_factory(
        user_id=user_id,
        service_id=1103,
        title="Unlinked service",
        service_date=(today + timedelta(days=3)).isoformat(),
    )

    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.execute(
            "update services set updated_at=? where id=?",
            ("2025-01-01T00:00:00", first_id),
        )
        db.execute(
            """
            insert into service_pco_links (
              service_id,
              pco_service_type_id,
              pco_plan_id,
              last_synced_at,
              last_sync_status
            ) values (?, ?, ?, ?, ?)
            """,
            (first_id, "type-1", "plan-1", "2025-01-02T00:00:00", "success"),
        )
        db.execute(
            """
            insert into service_pco_links (
              service_id,
              pco_service_type_id,
              pco_plan_id,
              last_synced_at,
              last_sync_status
            ) values (?, ?, ?, ?, ?)
            """,
            (second_id, "type-2", "plan-2", "2025-01-02T00:00:00", "failed"),
        )
        db.commit()

    response = client.get("/")
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    assert "PCO sync" in body
    assert "Synced" in body
    assert "Last sync failed" in body
    assert "Not linked" in body
    assert str(third_id) in body


def test_home_page_shows_not_connected_when_pco_feature_enabled(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(
        user_id=user_id,
        service_id=1201,
        title="Upcoming",
        service_date=(date.today() + timedelta(days=1)).isoformat(),
    )

    response = client.get("/")
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    assert "PCO sync" in body
    assert "Not connected" in body


def test_page_slug_renders_content(app, client):
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pages (slug, title, content) values (?, ?, ?)",
            ("custom-page", "Custom Page", "Hello **world**"),
        )
        db.commit()
    response = client.get("/custom-page")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Custom Page" in body
    assert "Hello" in body


def test_page_slug_missing_returns_404(client):
    response = client.get("/missing-page")
    assert response.status_code == 404
