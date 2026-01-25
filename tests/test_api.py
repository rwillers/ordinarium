from datetime import date

from ordinarium.db import get_db
from ordinarium.liturgical_calendar import resolve_season


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
