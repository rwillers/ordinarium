from datetime import date

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


def test_observance_endpoint_returns_options_for_date(client):
    response = client.get("/observance?date=2024-12-01")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["handle"] == "AdventI"
    assert payload["title"] == "The First Sunday in Advent"
    assert payload["season"] == "Advent"
    assert payload["options"]
