import json
import re
from datetime import date, timedelta

import ordinarium.service_share_routes as service_share_routes
import ordinarium.text_routes as text_routes
from ordinarium.db import get_db
from ordinarium.liturgical_calendar import resolve_observance, resolve_season
from ordinarium.plan_lessons import format_lesson_reference_with_biblia
from ordinarium.plan_propers import _load_collect_options
from ordinarium.service_store import load_service_for_text
from ordinarium.text_export import build_text_export_context


def _service_proper_override_rows(db):
    collect = db.execute(
        "select id, text from texts where type=? and filter_type=? order by id limit 1",
        ("collect", "proper"),
    ).fetchone()
    preface = db.execute(
        "select id, text from texts where type=? order by id limit 1",
        ("proper_preface",),
    ).fetchone()
    assert collect is not None
    assert preface is not None
    return collect, preface


def _first_content_excerpt(text, limit=40):
    if not text:
        return ""
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("######"):
            continue
        candidate = candidate.replace("*", "").strip()
        if len(candidate) > limit:
            return candidate[:limit]
        return candidate
    return ""


def _enable_pco_feature(app, user_id):
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set feature_flags=? where id=?",
            ('{"pco_sync": true}', user_id),
        )
        db.commit()


def _plan_row_token_for_title(html, title):
    pattern = re.compile(
        rf'data-plan-token="([^"]+)"\s+data-ordinary-title="{re.escape(title)}"'
    )
    match = pattern.search(html or "")
    return match.group(1) if match else ""


def _plan_row_token_for_detailed_title(html, detailed_title):
    pattern = re.compile(
        rf'data-plan-token="([^"]+)"[^>]*data-ordinary-detailed-title="{re.escape(detailed_title)}"'
    )
    match = pattern.search(html or "")
    return match.group(1) if match else ""


def _plan_row_token_for_custom_id(html, custom_id):
    pattern = re.compile(
        rf'data-plan-token="([^"]+)"[^>]*data-custom-id="{int(custom_id)}"'
    )
    match = pattern.search(html or "")
    return match.group(1) if match else ""


def test_services_new_redirects_to_next_id(auth_client, service_factory):
    client, user_id = auth_client
    service_factory(user_id=user_id, service_id=10)
    response = client.get("/services/new")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/services")


def test_services_new_copies_service_template(app, auth_client, service_factory):
    client, user_id = auth_client
    source_id = service_factory(
        user_id=user_id,
        service_id=20,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        text_order=json.dumps([68, 69]),
        text_disabled=json.dumps([]),
    )
    with app.app_context():
        db = get_db()
        collect_row, preface_row = _service_proper_override_rows(db)
        db.execute(
            "insert into service_custom_elements (service_id, user_id, title, text) values (?, ?, ?, ?)",
            (source_id, user_id, "Custom Blessing", "Custom text"),
        )
        element = db.execute(
            "select id from service_custom_elements where service_id=? and user_id=? limit 1",
            (source_id, user_id),
        ).fetchone()
        db.execute(
            "update services set text_order=?, text_disabled=?, proper_overrides=?, service_option_values=? where id=?",
            (
                json.dumps(["text:68", f"custom:{element['id']}", "text:69"]),
                json.dumps([f"custom:{element['id']}"]),
                json.dumps(
                    {
                        "collect_of_the_day": collect_row["id"],
                        "proper_preface": preface_row["id"],
                    }
                ),
                json.dumps({"lords_prayer.form": "contemporary"}),
                source_id,
            ),
        )
        db.commit()

    response = client.post(
        "/services",
        data={
            "mode": "copy",
            "from_service_id": str(source_id),
            "rite": "Renewed Ancient Text",
            "service_date": "2024-12-01",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/service/21")
    expected_date = "2024-12-01"
    parsed_date = date.fromisoformat(expected_date)
    observance = resolve_observance(parsed_date)
    expected_handle = observance.handle if observance else None
    expected_title = None
    if observance:
        expected_title = observance.name or observance.alternative_name or None
    with app.app_context():
        db = get_db()
        copied = db.execute(
            """
            select user_id, service_date, season, observance_handle, title, rite,
                   text_order, text_disabled, proper_overrides, service_option_values
            from services where id=? limit 1
            """,
            (21,),
        ).fetchone()
        assert copied["user_id"] == user_id
        assert copied["service_date"] == expected_date
        assert copied["season"] == resolve_season(parsed_date)
        assert copied["observance_handle"] == expected_handle
        assert copied["title"] == expected_title
        assert copied["rite"] == "Renewed Ancient Text"
        assert json.loads(copied["proper_overrides"] or "{}") == {
            "collect_of_the_day": collect_row["id"],
            "proper_preface": preface_row["id"],
        }
        assert json.loads(copied["service_option_values"] or "{}") == {
            "lords_prayer.form": "contemporary"
        }
        order_tokens = json.loads(copied["text_order"])
        disabled_tokens = json.loads(copied["text_disabled"])
        custom_elements = db.execute(
            "select id, title, text from service_custom_elements where service_id=?",
            (21,),
        ).fetchall()
        assert len(custom_elements) == 1
        new_custom_id = custom_elements[0]["id"]
        assert custom_elements[0]["title"] == "Custom Blessing"
        assert custom_elements[0]["text"] == "Custom text"
        assert order_tokens[1] == f"custom:{new_custom_id}"
        assert f"custom:{new_custom_id}" in disabled_tokens


def test_services_new_rejects_mismatched_rite(auth_client, service_factory):
    client, user_id = auth_client
    source_id = service_factory(
        user_id=user_id,
        service_id=22,
        service_date="2026-01-04",
        rite="Another Rite",
    )
    response = client.post(
        "/services",
        data={
            "mode": "copy",
            "from_service_id": str(source_id),
            "rite": "Renewed Ancient Text",
            "service_date": "2024-12-01",
        },
    )
    assert response.status_code == 400
    assert b"Service rite does not match" in response.data


def test_services_new_uses_selected_rite(app, auth_client, service_factory):
    client, user_id = auth_client
    service_factory(user_id=user_id, service_id=30)
    response = client.post(
        "/services",
        data={
            "mode": "defaults",
            "rite": "Anglican Standard Text",
            "service_date": "2024-12-01",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/service/31")
    with app.app_context():
        db = get_db()
        created = db.execute(
            "select rite from services where id=? limit 1", (31,)
        ).fetchone()
        assert created["rite"] == "Anglican Standard Text"


def test_services_page_uses_saved_default_rite_and_service_time(app, auth_client):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            update users
            set default_rite=?, default_service_time=?
            where id=?
            """,
            ("Anglican Standard Text", "08:15", user_id),
        )
        db.commit()

    response = client.get("/services")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert 'option value="Anglican Standard Text" selected' in body
    assert 'id="service-pco-default-time" value="08:15"' in body


def test_services_new_copies_non_default_rite(app, auth_client, service_factory):
    client, user_id = auth_client
    source_id = service_factory(
        user_id=user_id,
        service_id=40,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
    )
    response = client.post(
        "/services",
        data={
            "mode": "copy",
            "from_service_id": str(source_id),
            "rite": "Anglican Standard Text",
            "service_date": "2024-12-01",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/service/41")
    with app.app_context():
        db = get_db()
        copied = db.execute(
            "select rite from services where id=? limit 1", (41,)
        ).fetchone()
        assert copied["rite"] == "Anglican Standard Text"


def test_service_page_uses_saved_default_service_time_for_new_pco_plan(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(user_id=user_id, service_id=42, service_date="2099-01-04")
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set default_service_time=? where id=?",
            ("08:15", user_id),
        )
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.commit()

    response = client.get("/service/42")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert 'name="pco_plan_time" value="08:15"' in body


def test_services_multi_add_creates_services(app, auth_client):
    client, user_id = auth_client
    response = client.post(
        "/services",
        data={
            "add_mode": "multiple",
            "mode": "defaults",
            "rite": "Renewed Ancient Text",
            "multi_count": "2",
            "service_dates": ["2024-12-01", "2024-12-08"],
            "observance_handles": ["", ""],
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/services")
    with app.app_context():
        db = get_db()
        rows = db.execute(
            """
            select service_date, season, observance_handle, title
            from services
            where user_id=? and service_date in (?, ?)
            order by service_date asc
            """,
            (user_id, "2024-12-01", "2024-12-08"),
        ).fetchall()
        assert len(rows) == 2
        for row in rows:
            parsed_date = date.fromisoformat(row["service_date"])
            observance = resolve_observance(parsed_date)
            expected_handle = observance.handle if observance else None
            expected_title = None
            if observance:
                expected_title = observance.name or observance.alternative_name or None
            assert row["season"] == resolve_season(parsed_date)
            assert row["observance_handle"] == expected_handle
            assert row["title"] == expected_title


def test_services_tables_include_shared_pagination_config(auth_client, service_factory):
    client, user_id = auth_client
    today = date.today()
    service_factory(
        user_id=user_id,
        service_id=300,
        service_date=(today + timedelta(days=1)).isoformat(),
        title="Upcoming service",
    )
    service_factory(
        user_id=user_id,
        service_id=301,
        service_date=(today - timedelta(days=1)).isoformat(),
        title="Past service",
    )

    response = client.get("/services")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert (
        'id="services-upcoming-table" data-pagination="true" '
        'data-page-size="25" data-page-size-options="10,25,50,100"'
    ) in html
    assert (
        'id="services-past-table" data-pagination="true" '
        'data-page-size="25" data-page-size-options="10,25,50,100"'
    ) in html


def test_service_missing_id_returns_error(auth_client):
    client, _ = auth_client
    response = client.get("/service")
    assert response.status_code == 404


def test_service_denies_other_user(auth_client, service_factory, user_factory):
    client, _ = auth_client
    other_user_id = user_factory(email="other@example.com")
    service_factory(user_id=other_user_id, service_id=22, service_date="2026-01-04")
    response = client.get("/service/22")
    assert response.status_code == 404
    assert b"Service not found" in response.data


def test_service_pco_modal_shows_sync_button_when_unsynced(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_id = service_factory(
        user_id=user_id,
        service_id=230,
        service_date="2026-01-04",
        title="PCO service",
    )
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.execute(
            "update services set updated_at=? where id=?",
            ("2025-01-03T00:00:00", service_id),
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
            (service_id, "type-1", "plan-1", "2025-01-02T00:00:00", "success"),
        )
        db.commit()

    response = client.get(f"/service/{service_id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Sync service" in html
    assert "Remove link" in html


def test_service_pco_modal_hides_sync_button_when_synced(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_id = service_factory(
        user_id=user_id,
        service_id=231,
        service_date="2026-01-11",
        title="PCO synced service",
    )
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.execute(
            "update services set updated_at=? where id=?",
            ("2025-01-01T00:00:00", service_id),
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
            (service_id, "type-1", "plan-1", "2025-01-02T00:00:00", "success"),
        )
        db.commit()

    response = client.get(f"/service/{service_id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Sync service" not in html
    assert "Remove link" in html


def test_service_pco_prefill_uses_raw_observance_title(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_id = service_factory(
        user_id=user_id,
        service_id=232,
        service_date="2026-03-29",
        title="Palm Sunday",
    )
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.commit()

    response = client.get(f"/service/{service_id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-observance-title="Palm Sunday"' in html
    assert "(3/29/2026)" in html


def test_service_pco_templates_requires_service_type(app, auth_client, service_factory):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(user_id=user_id, service_id=233, service_date="2026-04-05")
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.commit()

    response = client.get("/service/233/pco/templates")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Service type is required" in payload["error"]


def test_service_pco_templates_requires_connection(app, auth_client, service_factory):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(user_id=user_id, service_id=234, service_date="2026-04-12")

    response = client.get("/service/234/pco/templates?service_type_id=type-1")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "not connected" in payload["error"].lower()


def test_service_pco_templates_denies_other_user(
    app, auth_client, service_factory, user_factory
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    other_user_id = user_factory(email="pco-template-other@example.com")
    service_factory(user_id=other_user_id, service_id=235, service_date="2026-04-19")
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.commit()

    response = client.get("/service/235/pco/templates?service_type_id=type-1")

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Service not found" in payload["error"]


def test_service_pco_templates_returns_normalized_rows(
    app, auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(user_id=user_id, service_id=236, service_date="2026-04-26")
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.commit()

    def fake_list_plan_templates(_base_url, _access_token, service_type_id):
        assert service_type_id == "type-1"
        return [
            {
                "id": "template-1",
                "attributes": {
                    "name": "Sunday teams",
                    "item_count": 2,
                    "team_count": 4,
                    "note_count": 1,
                },
            }
        ]

    monkeypatch.setattr(
        "ordinarium.service_pco_routes.list_plan_templates",
        fake_list_plan_templates,
    )

    response = client.get("/service/236/pco/templates?service_type_id=type-1")

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "templates": [
            {
                "id": "template-1",
                "name": "Sunday teams",
                "item_count": 2,
                "team_count": 4,
                "note_count": 1,
            }
        ],
    }


def test_service_pco_create_and_link_imports_selected_template(
    app, auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(user_id=user_id, service_id=237, service_date="2026-05-03")
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.commit()

    calls = []

    def fake_create_plan(
        _base_url, _access_token, service_type_id, title, plan_date, series_title
    ):
        calls.append(("create_plan", service_type_id, title, plan_date, series_title))
        return {"data": {"id": "plan-237", "attributes": {"title": title}}}

    def fake_create_plan_time(
        _base_url,
        _access_token,
        service_type_id,
        plan_id,
        plan_date,
        plan_time,
        tz_offset,
    ):
        calls.append(
            (
                "create_plan_time",
                service_type_id,
                plan_id,
                plan_date,
                plan_time,
                tz_offset,
            )
        )

    def fake_import_plan_template(
        _base_url, _access_token, service_type_id, plan_id, template_id
    ):
        calls.append(("import_plan_template", service_type_id, plan_id, template_id))

    monkeypatch.setattr("ordinarium.service_pco_routes.create_plan", fake_create_plan)
    monkeypatch.setattr(
        "ordinarium.service_pco_routes.create_plan_time", fake_create_plan_time
    )
    monkeypatch.setattr(
        "ordinarium.service_pco_routes.import_plan_template",
        fake_import_plan_template,
    )

    response = client.post(
        "/service/237/pco/link",
        data={
            "mode": "create",
            "pco_service_type_id": "type-1",
            "pco_service_type_name": "Sunday",
            "pco_plan_template_id": "template-1",
            "pco_plan_title": "Third Sunday of Easter",
            "pco_plan_date": "2026-05-03",
            "pco_plan_time": "10:00",
            "pco_plan_tz_offset": "0",
            "pco_series_title": "Easter",
        },
    )

    assert response.status_code == 302
    assert calls == [
        (
            "create_plan",
            "type-1",
            "Third Sunday of Easter",
            "2026-05-03",
            "Easter",
        ),
        ("create_plan_time", "type-1", "plan-237", "2026-05-03", "10:00", "0"),
        ("import_plan_template", "type-1", "plan-237", "template-1"),
    ]
    with app.app_context():
        db = get_db()
        link = db.execute(
            "select pco_service_type_id, pco_plan_id from service_pco_links where service_id=?",
            (237,),
        ).fetchone()
        assert link["pco_service_type_id"] == "type-1"
        assert link["pco_plan_id"] == "plan-237"


def test_service_pco_create_and_link_without_template_preserves_existing_behavior(
    app, auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(user_id=user_id, service_id=238, service_date="2026-05-10")
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.commit()

    import_calls = []

    monkeypatch.setattr(
        "ordinarium.service_pco_routes.create_plan",
        lambda *_args: {"data": {"id": "plan-238", "attributes": {"title": "Plan"}}},
    )
    monkeypatch.setattr(
        "ordinarium.service_pco_routes.create_plan_time",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "ordinarium.service_pco_routes.import_plan_template",
        lambda *_args: import_calls.append(_args),
    )

    response = client.post(
        "/service/238/pco/link",
        data={
            "mode": "create",
            "pco_service_type_id": "type-1",
            "pco_plan_title": "Plan",
            "pco_plan_date": "2026-05-10",
            "pco_plan_time": "10:00",
            "pco_plan_tz_offset": "0",
        },
    )

    assert response.status_code == 302
    assert import_calls == []


def test_service_pco_relink_clears_stale_item_links(
    app, auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_id = service_factory(
        user_id=user_id, service_id=239, service_date="2026-05-17"
    )
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.execute(
            """
            insert into service_pco_links (
              service_id,
              pco_service_type_id,
              pco_plan_id
            ) values (?, ?, ?)
            """,
            (service_id, "type-old", "plan-old"),
        )
        db.execute(
            """
            insert into service_pco_item_links (
              service_id,
              ordinarium_token,
              pco_item_id,
              last_content_hash,
              last_position
            ) values (?, ?, ?, ?, ?)
            """,
            (service_id, "text:1", "pco-old", "hash", 0),
        )
        db.commit()

    monkeypatch.setattr(
        "ordinarium.service_pco_routes.fetch_plan",
        lambda *_args: {
            "data": {"id": "plan-new", "attributes": {"title": "New plan"}}
        },
    )

    response = client.post(
        f"/service/{service_id}/pco/link",
        data={
            "mode": "existing",
            "pco_service_type_id": "type-new",
            "pco_service_type_name": "New service type",
            "pco_plan_id": "plan-new",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        db = get_db()
        item_count = db.execute(
            "select count(*) from service_pco_item_links where service_id=?",
            (service_id,),
        ).fetchone()[0]
        link = db.execute(
            "select pco_service_type_id, pco_plan_id from service_pco_links where service_id=?",
            (service_id,),
        ).fetchone()
        assert item_count == 0
        assert link["pco_service_type_id"] == "type-new"
        assert link["pco_plan_id"] == "plan-new"


def test_service_pco_unlink_clears_item_links(app, auth_client, service_factory):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_id = service_factory(
        user_id=user_id, service_id=240, service_date="2026-05-24"
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
            (service_id, "type-1", "plan-1"),
        )
        db.execute(
            """
            insert into service_pco_item_links (
              service_id,
              ordinarium_token,
              pco_item_id
            ) values (?, ?, ?)
            """,
            (service_id, "text:1", "pco-1"),
        )
        db.commit()

    response = client.post(f"/service/{service_id}/pco/unlink")

    assert response.status_code == 302
    with app.app_context():
        db = get_db()
        link_count = db.execute(
            "select count(*) from service_pco_links where service_id=?",
            (service_id,),
        ).fetchone()[0]
        item_count = db.execute(
            "select count(*) from service_pco_item_links where service_id=?",
            (service_id,),
        ).fetchone()[0]
        assert link_count == 0
        assert item_count == 0


def test_service_pco_sync_route_stores_delta_item_links(
    app, auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_id = service_factory(
        user_id=user_id, service_id=241, service_date="2026-05-31"
    )
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into pco_connections (user_id, access_token) values (?, ?)",
            (user_id, "token"),
        )
        db.execute(
            """
            insert into service_pco_links (
              service_id,
              pco_service_type_id,
              pco_plan_id
            ) values (?, ?, ?)
            """,
            (service_id, "type-1", "plan-1"),
        )
        db.commit()

    monkeypatch.setattr(
        "ordinarium.pco_sync._load_service_plan",
        lambda *_args: (
            {"id": service_id},
            [{"token": "text:1", "title": "Collect", "text": "Route sync text."}],
        ),
    )
    monkeypatch.setattr("ordinarium.pco_sync.list_plan_items", lambda *_args: [])
    monkeypatch.setattr(
        "ordinarium.pco_sync.create_plan_item",
        lambda *_args: {"data": {"id": "created-route-item"}},
    )

    response = client.post(
        f"/service/{service_id}/pco/sync",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["sync_status"] == "success"
    with app.app_context():
        db = get_db()
        link = db.execute(
            "select pco_item_id from service_pco_item_links where service_id=? and ordinarium_token=?",
            (service_id, "text:1"),
        ).fetchone()
        status = db.execute(
            "select last_sync_status from service_pco_links where service_id=?",
            (service_id,),
        ).fetchone()
        assert link["pco_item_id"] == "created-route-item"
        assert status["last_sync_status"] == "success"


def test_service_delete_removes_related_rows(app, auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(user_id=user_id, service_id=31)
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into service_custom_elements (service_id, user_id, title, text) values (?, ?, ?, ?)",
            (service_id, user_id, "Custom Blessing", "Custom text"),
        )
        db.execute(
            "insert into service_shares (service_id, share_uuid) values (?, ?)",
            (service_id, "share-uuid-1"),
        )
        db.commit()

    response = client.post(f"/service/{service_id}/delete")
    assert response.status_code == 302

    with app.app_context():
        db = get_db()
        element_count = db.execute(
            "select count(*) from service_custom_elements where service_id=?",
            (service_id,),
        ).fetchone()[0]
        share_count = db.execute(
            "select count(*) from service_shares where service_id=?",
            (service_id,),
        ).fetchone()[0]
        assert element_count == 0
        assert share_count == 0


def test_services_bulk_delete_removes_selected_rows(
    app, auth_client, service_factory, user_factory
):
    client, user_id = auth_client
    other_user_id = user_factory(email="other-bulk@example.com")
    service_id_one = service_factory(user_id=user_id, service_id=90)
    service_id_two = service_factory(user_id=user_id, service_id=91)
    other_service_id = service_factory(user_id=other_user_id, service_id=92)
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into service_custom_elements (service_id, user_id, title, text) values (?, ?, ?, ?)",
            (service_id_one, user_id, "Custom Blessing", "Custom text"),
        )
        db.execute(
            "insert into service_shares (service_id, share_uuid) values (?, ?)",
            (service_id_one, "share-uuid-bulk"),
        )
        db.commit()

    response = client.post(
        "/services/bulk-delete",
        data={
            "service_ids": [
                str(service_id_one),
                str(service_id_two),
                str(other_service_id),
            ]
        },
    )
    assert response.status_code == 302

    with app.app_context():
        db = get_db()
        remaining = db.execute(
            "select id from services where id in (?, ?, ?)",
            (service_id_one, service_id_two, other_service_id),
        ).fetchall()
        remaining_ids = {row["id"] for row in remaining}
        assert service_id_one not in remaining_ids
        assert service_id_two not in remaining_ids
        assert other_service_id in remaining_ids
        element_count = db.execute(
            "select count(*) from service_custom_elements where service_id=?",
            (service_id_one,),
        ).fetchone()[0]
        share_count = db.execute(
            "select count(*) from service_shares where service_id=?",
            (service_id_one,),
        ).fetchone()[0]
        assert element_count == 0
        assert share_count == 0


def test_service_plan_uses_saved_rite_ordinaries(auth_client, service_factory):
    client, user_id = auth_client
    service_factory(user_id=user_id, service_id=60, rite="Anglican Standard Text")
    response = client.get("/service/60")
    assert response.status_code == 200
    assert b"Anglican Standard Text" in response.data
    assert b"text:1276" in response.data


def test_persist_service_requires_date(auth_client, service_factory):
    client, user_id = auth_client
    service_factory(user_id=user_id, service_id=5, rite="Renewed Ancient Text")
    response = client.patch(
        "/service/5",
        data={"rite": "Renewed Ancient Text", "ids": "68,69"},
    )
    assert response.status_code == 400
    assert b"Service date is required." in response.data


def test_persist_service_autosave_requires_date(auth_client, service_factory):
    client, user_id = auth_client
    service_factory(user_id=user_id, service_id=5, rite="Renewed Ancient Text")
    response = client.patch(
        "/service/5",
        data={
            "rite": "Renewed Ancient Text",
            "ids": "68,69",
            "autosave": "1",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Service date is required" in payload["error"]


def test_persist_service_saves_and_generates_text(app, auth_client, service_factory):
    client, user_id = auth_client
    service_factory(user_id=user_id, service_id=7, rite="Renewed Ancient Text")
    response = client.patch(
        "/service/7",
        data={
            "rite": "Renewed Ancient Text",
            "service_date": "2026-01-04",
            "ids": "68,69",
            "disabled": "69",
            "action": "generate",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/service/7/view")
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select user_id, service_date from services where id=? limit 1", (7,)
        ).fetchone()
        assert service["user_id"] == user_id
        assert service["service_date"] == "2026-01-04"


def test_persist_service_autosave_saves_data(app, auth_client, service_factory):
    client, user_id = auth_client
    service_factory(user_id=user_id, service_id=8, rite="Renewed Ancient Text")
    response = client.patch(
        "/service/8",
        data={
            "rite": "Renewed Ancient Text",
            "service_date": "2026-01-04",
            "ids": "68,69",
            "autosave": "1",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    lesson_defaults = payload["lesson_defaults"]
    assert isinstance(lesson_defaults, dict)
    assert set(lesson_defaults.keys()) == {
        "lesson_1",
        "psalm",
        "lesson_2",
        "gospel",
    }
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select user_id, service_date from services where id=? limit 1", (8,)
        ).fetchone()
        assert service["user_id"] == user_id
        assert service["service_date"] == "2026-01-04"


def test_persist_service_preserves_service_option_values(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_factory(
        user_id=user_id,
        service_id=81,
        rite="Renewed Ancient Text",
        service_option_values={"lords_prayer.form": "contemporary"},
    )
    response = client.patch(
        "/service/81",
        data={
            "rite": "Renewed Ancient Text",
            "service_date": "2026-01-04",
            "ids": "68,69",
            "autosave": "1",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select service_option_values from services where id=? limit 1",
            (81,),
        ).fetchone()
        assert json.loads(service["service_option_values"] or "{}") == {
            "lords_prayer.form": "contemporary"
        }


def test_persist_service_invalid_id_returns_error(app, auth_client):
    client, _ = auth_client
    with app.app_context():
        db = get_db()
        before = db.execute("select count(*) as count from services").fetchone()[
            "count"
        ]
    response = client.patch(
        "/service/not-a-number",
        data={
            "rite": "Renewed Ancient Text",
            "service_date": "2026-01-04",
            "ids": "68,69",
        },
    )
    assert response.status_code == 404
    with app.app_context():
        db = get_db()
        after = db.execute("select count(*) as count from services").fetchone()["count"]
        assert after == before


def test_persist_service_normalizes_observance_handle(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_factory(user_id=user_id, service_id=12, rite="Renewed Ancient Text")
    response = client.patch(
        "/service/12",
        data={
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
            "select user_id, observance_handle, title from services where id=? limit 1",
            (12,),
        ).fetchone()
        assert service["user_id"] == user_id
        assert service["observance_handle"] == "AdventI"
        assert service["title"] == "The First Sunday in Advent"


def test_persist_service_autosave_denies_other_user(
    auth_client, service_factory, user_factory
):
    client, _ = auth_client
    other_user_id = user_factory(email="other-autosave@example.com")
    service_factory(user_id=other_user_id, service_id=90, service_date="2026-01-04")
    response = client.patch(
        "/service/90",
        data={
            "rite": "Renewed Ancient Text",
            "service_date": "2026-01-04",
            "ids": "68,69",
            "autosave": "1",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Service not found" in payload["error"]


def test_text_missing_service_returns_error(auth_client):
    client, _ = auth_client
    response = client.get("/service/999/view")
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
    response = client.get("/service/14/view")
    assert response.status_code == 200
    assert b"Holy Eucharist" in response.data


def test_text_renders_biblia_link_for_lesson_override(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=15,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        lesson_overrides={"lesson_1": "Genesis 1:1-5"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'class="lesson-reference-link"' in body
    assert 'href="https://biblia.com/books/esv/Gen1.1-5"' in body
    assert 'target="_blank"' in body
    assert 'rel="noopener noreferrer"' in body
    assert ">Genesis 1:1-5<" in body


def test_text_renders_biblia_link_using_saved_translation(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set default_bible_translation=? where id=?",
            ("NIV", user_id),
        )
        db.commit()
    service_id = service_factory(
        user_id=user_id,
        service_id=16,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        lesson_overrides={"lesson_1": "Genesis 1:1-5"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'href="https://biblia.com/books/niv2011/Gen1.1-5"' in body
    assert 'href="https://biblia.com/books/esv/Gen1.1-5"' not in body


def test_shared_text_uses_service_owner_bible_translation(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=17,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        lesson_overrides={"lesson_1": "Genesis 1:1-5"},
    )
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set default_bible_translation=? where id=?",
            ("NRSV", user_id),
        )
        db.execute(
            "insert into service_shares (service_id, share_uuid) values (?, ?)",
            (service_id, "lesson-link-share"),
        )
        db.commit()
    response = client.get("/share/lesson-link-share")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'href="https://biblia.com/books/nrsv/Gen1.1-5"' in body


def test_text_export_docx_returns_attachment(auth_client, service_factory, monkeypatch):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=114,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    monkeypatch.setattr(
        text_routes, "render_docx_bytes", lambda context: b"PK\x03\x04docx"
    )
    response = client.get(f"/service/{service_id}/export.docx")
    assert response.status_code == 200
    assert (
        response.mimetype
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "attachment;" in response.headers["Content-Disposition"]
    assert response.data.startswith(b"PK\x03\x04")


def test_text_export_pdf_returns_attachment(auth_client, service_factory, monkeypatch):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=115,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    monkeypatch.setattr(
        text_routes,
        "render_pdf_bytes",
        lambda html_text, base_url=None: b"%PDF-1.7\nfake\n",
    )
    response = client.get(f"/service/{service_id}/export.pdf")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert "attachment;" in response.headers["Content-Disposition"]
    assert response.data.startswith(b"%PDF-1.7")


def test_text_export_dependency_error_returns_503(
    auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=116,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )

    def raise_missing_dependency(_context):
        raise RuntimeError("DOCX export requires python-docx to be installed.")

    monkeypatch.setattr(text_routes, "render_docx_bytes", raise_missing_dependency)
    response = client.get(f"/service/{service_id}/export.docx")
    assert response.status_code == 503
    assert b"python-docx" in response.data


def test_text_export_pdf_runtime_error_returns_503(
    auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=117,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )

    def raise_pdf_runtime_error(_html_text, base_url=None):
        raise RuntimeError("PDF export failed in WeasyPrint runtime.")

    monkeypatch.setattr(text_routes, "render_pdf_bytes", raise_pdf_runtime_error)
    response = client.get(f"/service/{service_id}/export.pdf")
    assert response.status_code == 503
    assert b"Unable to generate PDF at this time." in response.data


def test_text_export_pdf_unexpected_error_returns_503(
    auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=118,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )

    def raise_pdf_unknown_error(_html_text, base_url=None):
        raise ValueError("unexpected")

    monkeypatch.setattr(text_routes, "render_pdf_bytes", raise_pdf_unknown_error)
    response = client.get(f"/service/{service_id}/export.pdf")
    assert response.status_code == 503
    assert b"Unable to generate PDF at this time." in response.data


def test_lesson_override_updates_service(app, auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=25,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.post(
        f"/service/{service_id}/lesson-passage",
        data={
            "lesson_key": "gospel",
            "lesson_mode": "custom",
            "custom_passage": "Mark 1:1-8",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["custom_passage"] == "Mark 1:1-8"
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select lesson_overrides from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        saved = json.loads(service["lesson_overrides"])
        assert saved["gospel"] == "Mark 1:1-8"

    response = client.post(
        f"/service/{service_id}/lesson-passage",
        data={"lesson_key": "gospel", "lesson_mode": "default"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select lesson_overrides from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        saved = json.loads(service["lesson_overrides"] or "{}")
        assert "gospel" not in saved


def test_lesson_override_updates_service_with_canonical_option(
    app, auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=319,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )

    def fake_alternates(_service_date, _observance_handle):
        return {"gospel": ["Mark (1:9-13)", "John (1:29-34)"]}

    monkeypatch.setattr(
        service_share_routes,
        "_resolve_lesson_reference_alternates",
        fake_alternates,
    )

    response = client.post(
        f"/service/{service_id}/lesson-passage",
        data={
            "lesson_key": "gospel",
            "lesson_mode": "canonical",
            "canonical_passage": "Mark (1:9-13)",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["mode"] == "canonical"
    assert payload["custom_passage"] == "Mark (1:9-13)"
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select lesson_overrides from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        saved = json.loads(service["lesson_overrides"] or "{}")
        assert saved["gospel"] == "Mark (1:9-13)"


def test_lesson_override_rejects_invalid_canonical_option(
    auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=320,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )

    def fake_alternates(_service_date, _observance_handle):
        return {"gospel": ["Mark (1:9-13)"]}

    monkeypatch.setattr(
        service_share_routes,
        "_resolve_lesson_reference_alternates",
        fake_alternates,
    )

    response = client.post(
        f"/service/{service_id}/lesson-passage",
        data={
            "lesson_key": "gospel",
            "lesson_mode": "canonical",
            "canonical_passage": "Luke (3:1-6)",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Canonical lesson option is invalid." in payload["error"]


def test_text_uses_lesson_override(app, auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=26,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    with app.app_context():
        db = get_db()
        db.execute(
            "update services set lesson_overrides=? where id=?",
            (json.dumps({"gospel": "Mark 1:1-8"}), service_id),
        )
        db.commit()
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    assert b"Mark 1:1-8" in response.data


def test_proper_override_updates_service(app, auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=27,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    with app.app_context():
        db = get_db()
        collect_row, preface_row = _service_proper_override_rows(db)
    response = client.post(
        f"/service/{service_id}/proper-override",
        data={
            "proper_key": "collect_of_the_day",
            "proper_mode": "custom",
            "proper_text_id": str(collect_row["id"]),
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["proper_key"] == "collect_of_the_day"
    assert payload["proper_text_id"] == collect_row["id"]

    response = client.post(
        f"/service/{service_id}/proper-override",
        data={
            "proper_key": "proper_preface",
            "proper_mode": "custom",
            "proper_text_id": str(preface_row["id"]),
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["proper_key"] == "proper_preface"
    assert payload["proper_text_id"] == preface_row["id"]

    with app.app_context():
        db = get_db()
        service = db.execute(
            "select proper_overrides from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        saved = json.loads(service["proper_overrides"] or "{}")
        assert saved == {
            "collect_of_the_day": collect_row["id"],
            "proper_preface": preface_row["id"],
        }

    response = client.post(
        f"/service/{service_id}/proper-override",
        data={"proper_key": "proper_preface", "proper_mode": "default"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["proper_text_id"] is None
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select proper_overrides from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        saved = json.loads(service["proper_overrides"] or "{}")
        assert saved == {"collect_of_the_day": collect_row["id"]}


def test_text_uses_proper_overrides(app, auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=28,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    with app.app_context():
        db = get_db()
        collect_row, preface_row = _service_proper_override_rows(db)
        db.execute(
            "update services set proper_overrides=? where id=?",
            (
                json.dumps(
                    {
                        "collect_of_the_day": collect_row["id"],
                        "proper_preface": preface_row["id"],
                    }
                ),
                service_id,
            ),
        )
        db.commit()
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    collect_excerpt = _first_content_excerpt(collect_row["text"])
    preface_excerpt = _first_content_excerpt(preface_row["text"])
    assert collect_excerpt
    assert preface_excerpt
    assert collect_excerpt in html
    assert preface_excerpt in html


def test_service_option_route_updates_and_clears_option(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=284,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "lords_prayer.form", "option_value": "contemporary"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "lords_prayer.form"
    assert payload["option_value"] == "contemporary"
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select service_option_values from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        assert json.loads(service["service_option_values"] or "{}") == {
            "lords_prayer.form": "contemporary"
        }
    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "lords_prayer.form", "option_value": ""},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_value"] is None
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select service_option_values from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        assert json.loads(service["service_option_values"] or "{}") == {}


def test_service_option_route_updates_alleluia_mode_keys(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=287,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "fraction.alleluia_mode", "option_value": "off"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "fraction.alleluia_mode"
    assert payload["option_value"] == "off"
    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "dismissal.alleluia_mode", "option_value": "on"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "dismissal.alleluia_mode"
    assert payload["option_value"] == "on"
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select service_option_values from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        assert json.loads(service["service_option_values"] or "{}") == {
            "fraction.alleluia_mode": "off",
            "dismissal.alleluia_mode": "on",
        }


def test_service_option_route_updates_fraction_and_communion_form_keys(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=295,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "fraction.form",
            "option_value": "passover_lamb_has_been_sacrificed",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "fraction.form"
    assert payload["option_value"] == "passover_lamb_has_been_sacrificed"

    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "communion.invitation.form", "option_value": "behold_lamb"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "communion.invitation.form"
    assert payload["option_value"] == "behold_lamb"

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "communion.invitation.appended_clause",
            "option_value": "omit",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "communion.invitation.appended_clause"
    assert payload["option_value"] == "omit"

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "communion.invitation.appended_text",
            "option_value": "Take and eat in remembrance that Christ died for you.",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "communion.invitation.appended_text"
    assert (
        payload["option_value"]
        == "Take and eat in remembrance that Christ died for you."
    )

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "communion.distribution.body_clause",
            "option_value": "include",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "communion.distribution.body_clause"
    assert payload["option_value"] == "include"

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "communion.distribution.body_text",
            "option_value": "which was given for you, preserve you in everlasting life.",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "communion.distribution.body_text"
    assert (
        payload["option_value"]
        == "which was given for you, preserve you in everlasting life."
    )

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "communion.distribution.blood_clause",
            "option_value": "omit",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "communion.distribution.blood_clause"
    assert payload["option_value"] == "omit"

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "communion.distribution.blood_text",
            "option_value": "which was shed for you, keep you faithful unto death.",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "communion.distribution.blood_text"
    assert (
        payload["option_value"]
        == "which was shed for you, keep you faithful unto death."
    )

    with app.app_context():
        db = get_db()
        service = db.execute(
            "select service_option_values from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        assert json.loads(service["service_option_values"] or "{}") == {
            "fraction.form": "passover_lamb_has_been_sacrificed",
            "communion.invitation.form": "behold_lamb",
            "communion.invitation.appended_clause": "omit",
            "communion.invitation.appended_text": "Take and eat in remembrance that Christ died for you.",
            "communion.distribution.body_clause": "include",
            "communion.distribution.body_text": "which was given for you, preserve you in everlasting life.",
            "communion.distribution.blood_clause": "omit",
            "communion.distribution.blood_text": "which was shed for you, keep you faithful unto death.",
        }


def test_service_options_route_updates_multiple_keys_in_single_request(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=322,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
    )
    response = client.post(
        f"/service/{service_id}/service-options",
        json={
            "option_values": {
                "prayers.form": "ast",
                "prayers.adversity.especially_clause": "omit",
                "prayers.adversity.especially_names": "those in need of mercy",
                "communion.invitation.form": "gifts_of_god",
            }
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["service_option_values"]["prayers.form"] == "ast"
    assert (
        payload["service_option_values"]["prayers.adversity.especially_clause"]
        == "omit"
    )
    assert (
        payload["service_option_values"]["prayers.adversity.especially_names"]
        == "those in need of mercy"
    )
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select service_option_values from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        assert json.loads(service["service_option_values"] or "{}") == {
            "prayers.form": "ast",
            "prayers.adversity.especially_clause": "omit",
            "prayers.adversity.especially_names": "those in need of mercy",
            "communion.invitation.form": "gifts_of_god",
        }


def test_service_option_preview_route_returns_rendered_row_html(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=323,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
    )
    service_response = client.get(f"/service/{service_id}")
    assert service_response.status_code == 200
    row_token = _plan_row_token_for_title(
        service_response.get_data(as_text=True),
        "The Prayers of the People",
    )
    assert row_token
    preview_response = client.post(
        f"/service/{service_id}/service-option-preview",
        json={
            "row_token": row_token,
            "option_values": {
                "prayers.adversity.especially_clause": "include",
                "prayers.adversity.especially_names": "those in need of healing",
            },
        },
        headers={"Accept": "application/json"},
    )
    assert preview_response.status_code == 200
    payload = preview_response.get_json()
    assert payload["ok"] is True
    preview_html = payload["preview_html"] or ""
    assert "those in need of healing" in preview_html
    assert "[especially _____________]" not in preview_html


def test_service_option_preview_route_renders_decalogue_text(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=337,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
    )
    service_response = client.get(f"/service/{service_id}")
    assert service_response.status_code == 200
    row_token = _plan_row_token_for_title(
        service_response.get_data(as_text=True),
        "The Summary of the Law",
    )
    assert row_token
    preview_response = client.post(
        f"/service/{service_id}/service-option-preview",
        json={
            "row_token": row_token,
            "option_values": {"law.form": "decalogue"},
        },
        headers={"Accept": "application/json"},
    )
    assert preview_response.status_code == 200
    payload = preview_response.get_json()
    assert payload["ok"] is True
    preview_html = payload["preview_html"] or ""
    assert "Then follows the Decalogue (page 100)." in preview_html
    assert "You shall have no other gods but me." in preview_html
    assert "Hear what our Lord Jesus Christ says:" not in preview_html


def test_service_option_preview_route_applies_lesson_override_patch(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=326,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    service_response = client.get(f"/service/{service_id}")
    assert service_response.status_code == 200
    row_token = _plan_row_token_for_detailed_title(
        service_response.get_data(as_text=True),
        "The Lessons (1)",
    )
    assert row_token
    preview_response = client.post(
        f"/service/{service_id}/service-option-preview",
        json={
            "row_token": row_token,
            "option_values": {},
            "lesson_override": {
                "lesson_key": "lesson_1",
                "mode": "custom",
                "custom_passage": "Genesis 1:1-5",
            },
        },
        headers={"Accept": "application/json"},
    )
    assert preview_response.status_code == 200
    payload = preview_response.get_json()
    assert payload["ok"] is True
    preview_html = payload["preview_html"] or ""
    assert 'class="lesson-reference-link"' in preview_html
    assert "Genesis 1:1-5" in preview_html
    assert 'href="https://biblia.com/books/esv/Gen1.1-5"' in preview_html
    assert 'target="_blank"' in preview_html


def test_service_option_preview_route_leaves_unparseable_lesson_override_plain_text(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=338,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    service_response = client.get(f"/service/{service_id}")
    assert service_response.status_code == 200
    row_token = _plan_row_token_for_detailed_title(
        service_response.get_data(as_text=True),
        "The Lessons (1)",
    )
    assert row_token
    preview_response = client.post(
        f"/service/{service_id}/service-option-preview",
        json={
            "row_token": row_token,
            "option_values": {},
            "lesson_override": {
                "lesson_key": "lesson_1",
                "mode": "custom",
                "custom_passage": "Gospel reading TBD",
            },
        },
        headers={"Accept": "application/json"},
    )
    assert preview_response.status_code == 200
    payload = preview_response.get_json()
    assert payload["ok"] is True
    preview_html = payload["preview_html"] or ""
    assert "Gospel reading TBD" in preview_html
    assert "href=" not in preview_html


def test_build_text_export_context_keeps_lesson_references_plain_text(
    app, auth_client, service_factory
):
    _client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=339,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        lesson_overrides={"lesson_1": "Genesis 1:1-5"},
    )
    with app.app_context():
        saved_service, saved_data = load_service_for_text(service_id, user_id)
        context = build_text_export_context(
            service_id,
            saved_service,
            saved_data,
            user_id=user_id,
        )
    assert context is not None
    lesson_row = next(
        (
            item
            for item in context["ordinaries"]
            if item["title_markdown"] == "The Lessons"
        ),
        None,
    )
    assert lesson_row is not None
    assert "Genesis 1:1-5" in lesson_row["body_html"]
    assert "<a " not in lesson_row["body_html"]


def test_format_lesson_reference_with_biblia_links_structured_psalm_reference():
    lesson = {
        "book": "Ps",
        "book_name": "Psalm",
        "reference_short": "1:1-3",
        "reference_long": "1:1-3",
    }
    linked = format_lesson_reference_with_biblia(
        "Psalm (1:1-3)",
        "ESV",
        lesson=lesson,
    )
    assert linked == "[Psalm (1:1-3)](https://biblia.com/books/esv/Ps1.1-3)"


def test_format_lesson_reference_with_biblia_links_roman_numeral_book_display():
    linked = format_lesson_reference_with_biblia(
        "I Corinthians (1:1-9)",
        "NRSV",
    )
    assert linked == "[I Corinthians (1:1-9)](https://biblia.com/books/nrsv/1Cor1.1-9)"


def test_format_lesson_reference_with_biblia_truncates_gap_references_after_comma():
    linked = format_lesson_reference_with_biblia(
        "John (9:1-13, 28-41)",
        "NRSV",
    )
    assert linked == "[John (9:1-13, 28-41)](https://biblia.com/books/nrsv/John9.1-13)"


def test_format_lesson_reference_with_biblia_leaves_unknown_reference_unlinked():
    linked = format_lesson_reference_with_biblia(
        "Canticle (Benedictus)",
        "ESV",
    )
    assert linked == "Canticle (Benedictus)"


def test_service_option_preview_route_marks_custom_rows(
    auth_client, service_factory, app
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=332,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into service_custom_elements (service_id, user_id, title, text) values (?, ?, ?, ?)",
            (
                service_id,
                user_id,
                "Custom prayer",
                "- One custom petition\n- Another custom petition",
            ),
        )
        db.commit()
        custom_row = db.execute(
            "select id from service_custom_elements where service_id=? and user_id=? order by id desc limit 1",
            (service_id, user_id),
        ).fetchone()
        assert custom_row is not None
        custom_id = custom_row["id"]

    service_response = client.get(f"/service/{service_id}")
    assert service_response.status_code == 200
    row_token = _plan_row_token_for_custom_id(
        service_response.get_data(as_text=True),
        custom_id,
    )
    assert row_token
    preview_response = client.post(
        f"/service/{service_id}/service-option-preview",
        json={"row_token": row_token, "option_values": {}},
        headers={"Accept": "application/json"},
    )
    assert preview_response.status_code == 200
    payload = preview_response.get_json()
    assert payload["ok"] is True
    assert payload["is_custom"] is True
    assert "custom petition" in (payload["preview_html"] or "")


def test_service_option_preview_route_matches_rows_by_token_not_index(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=331,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={"penitential_song.mode": "trisagion"},
    )
    service_response = client.get(f"/service/{service_id}")
    assert service_response.status_code == 200
    service_html = service_response.get_data(as_text=True)

    collect_token = _plan_row_token_for_title(service_html, "The Collect of the Day")
    dismissal_token = _plan_row_token_for_title(service_html, "The Dismissal")
    post_communion_token = _plan_row_token_for_title(
        service_html, "The Post Communion Prayer"
    )
    assert collect_token
    assert dismissal_token
    assert post_communion_token

    collect_preview = client.post(
        f"/service/{service_id}/service-option-preview",
        json={"row_token": collect_token, "option_values": {}},
        headers={"Accept": "application/json"},
    )
    assert collect_preview.status_code == 200
    collect_payload = collect_preview.get_json()
    assert collect_payload["ok"] is True
    assert collect_payload["title"] == "The Collect of the Day"

    dismissal_preview = client.post(
        f"/service/{service_id}/service-option-preview",
        json={"row_token": dismissal_token, "option_values": {}},
        headers={"Accept": "application/json"},
    )
    assert dismissal_preview.status_code == 200
    dismissal_payload = dismissal_preview.get_json()
    assert dismissal_payload["ok"] is True
    assert dismissal_payload["title"] == "The Dismissal"

    post_default_preview = client.post(
        f"/service/{service_id}/service-option-preview",
        json={"row_token": post_communion_token, "option_values": {}},
        headers={"Accept": "application/json"},
    )
    assert post_default_preview.status_code == 200
    post_default_payload = post_default_preview.get_json()
    assert post_default_payload["ok"] is True
    assert post_default_payload["title"] == "The Post Communion Prayer"

    post_swap_preview = client.post(
        f"/service/{service_id}/service-option-preview",
        json={
            "row_token": post_communion_token,
            "option_values": {"post_communion.form": "other_rite"},
        },
        headers={"Accept": "application/json"},
    )
    assert post_swap_preview.status_code == 200
    post_swap_payload = post_swap_preview.get_json()
    assert post_swap_payload["ok"] is True
    assert post_swap_payload["title"] == "The Post Communion Prayer"
    assert post_swap_payload["preview_html"] != post_default_payload["preview_html"]


def test_service_option_preview_route_applies_kyrie_form_selection(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=333,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    service_response = client.get(f"/service/{service_id}")
    assert service_response.status_code == 200
    row_token = _plan_row_token_for_title(
        service_response.get_data(as_text=True),
        "The Kyrie",
    )
    assert row_token

    greek_response = client.post(
        f"/service/{service_id}/service-option-preview",
        json={
            "row_token": row_token,
            "option_values": {
                "penitential_song.mode": "kyrie",
                "kyrie.form": "greek",
            },
        },
        headers={"Accept": "application/json"},
    )
    assert greek_response.status_code == 200
    greek_payload = greek_response.get_json()
    greek_html = greek_payload["preview_html"] or ""
    assert greek_payload["ok"] is True
    assert "Kyrie eleison." in greek_html
    assert "Lord, have mercy upon us." not in greek_html

    contemporary_response = client.post(
        f"/service/{service_id}/service-option-preview",
        json={
            "row_token": row_token,
            "option_values": {
                "penitential_song.mode": "kyrie",
                "kyrie.form": "contemporary",
            },
        },
        headers={"Accept": "application/json"},
    )
    assert contemporary_response.status_code == 200
    contemporary_payload = contemporary_response.get_json()
    contemporary_html = contemporary_payload["preview_html"] or ""
    assert contemporary_payload["ok"] is True
    assert "Lord, have mercy." in contemporary_html
    assert "Lord, have mercy upon us." not in contemporary_html
    assert "Kyrie eleison." not in contemporary_html

    trisagion_response = client.post(
        f"/service/{service_id}/service-option-preview",
        json={
            "row_token": row_token,
            "option_values": {
                "penitential_song.mode": "trisagion",
            },
        },
        headers={"Accept": "application/json"},
    )
    assert trisagion_response.status_code == 200
    trisagion_payload = trisagion_response.get_json()
    trisagion_html = trisagion_payload["preview_html"] or ""
    assert trisagion_payload["ok"] is True
    assert "Holy God," in trisagion_html
    assert "Kyrie eleison." not in trisagion_html


def test_service_option_route_updates_filioque_clause_key(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=300,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "creed.filioque_clause", "option_value": "omit"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "creed.filioque_clause"
    assert payload["option_value"] == "omit"
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select service_option_values from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        assert json.loads(service["service_option_values"] or "{}") == {
            "creed.filioque_clause": "omit"
        }


def test_service_option_route_updates_comfortable_words_sentences_key(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=317,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "comfortable_words.sentences",
            "option_value": json.dumps(["matthew_11_28", "first_timothy_1_15"]),
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "comfortable_words.sentences"
    assert payload["option_value"] == ["matthew_11_28", "first_timothy_1_15"]
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select service_option_values from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        assert json.loads(service["service_option_values"] or "{}") == {
            "comfortable_words.sentences": ["matthew_11_28", "first_timothy_1_15"]
        }


def test_service_option_route_updates_prayers_clause_keys(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=303,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    for option_key, option_value in (
        ("prayers.adversity.especially_clause", "omit"),
        ("prayers.departed.especially_clause", "include"),
        ("prayers.public_service.especially_clause", "omit"),
        ("prayers.public_service.especially_names", "our mayor and council"),
        ("prayers.adversity.especially_names", "those in recovery"),
        ("prayers.departed.especially_names", "N., N., and N."),
    ):
        response = client.post(
            f"/service/{service_id}/service-option",
            data={"option_key": option_key, "option_value": option_value},
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["option_key"] == option_key
        assert payload["option_value"] == option_value
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select service_option_values from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        assert json.loads(service["service_option_values"] or "{}") == {
            "prayers.adversity.especially_clause": "omit",
            "prayers.departed.especially_clause": "include",
            "prayers.public_service.especially_clause": "omit",
            "prayers.public_service.especially_names": "our mayor and council",
            "prayers.adversity.especially_names": "those in recovery",
            "prayers.departed.especially_names": "N., N., and N.",
        }


def test_service_option_route_updates_ast_prayers_named_person_key(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=307,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
    )
    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "prayers.saints.named_person", "option_value": "St. Mary"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["option_key"] == "prayers.saints.named_person"
    assert payload["option_value"] == "St. Mary"
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select service_option_values from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        assert json.loads(service["service_option_values"] or "{}") == {
            "prayers.saints.named_person": "St. Mary"
        }


def test_service_option_route_updates_ast_prayers_profile_keys(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=310,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
    )
    for option_key, option_value in (
        ("prayers.ast.profile", "commonwealth"),
        ("prayers.ast.civil_leader.name", "Jane Doe"),
        ("prayers.ast.civil_leader.title", "prime_minister"),
        ("prayers.ast.clergy.name", "Bp. John"),
        ("prayers.ast.clergy.title", "bishop"),
    ):
        response = client.post(
            f"/service/{service_id}/service-option",
            data={"option_key": option_key, "option_value": option_value},
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["option_key"] == option_key
        assert payload["option_value"] == option_value
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select service_option_values from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        assert json.loads(service["service_option_values"] or "{}") == {
            "prayers.ast.profile": "commonwealth",
            "prayers.ast.civil_leader.name": "Jane Doe",
            "prayers.ast.civil_leader.title": "prime_minister",
            "prayers.ast.clergy.name": "Bp. John",
            "prayers.ast.clergy.title": "bishop",
        }


def test_service_option_route_updates_cross_rite_swap_keys(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=314,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    for option_key, option_value in (
        ("prayers.form", "ast"),
        ("post_communion.form", "other_rite"),
    ):
        response = client.post(
            f"/service/{service_id}/service-option",
            data={"option_key": option_key, "option_value": option_value},
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["option_key"] == option_key
        assert payload["option_value"] == option_value
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select service_option_values from services where id=? limit 1",
            (service_id,),
        ).fetchone()
        assert json.loads(service["service_option_values"] or "{}") == {
            "prayers.form": "ast",
            "post_communion.form": "other_rite",
        }


def test_service_option_route_rejects_invalid_values(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=285,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "lords_prayer.form", "option_value": "invalid"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "fraction.alleluia_mode", "option_value": "maybe"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "creed.filioque_clause", "option_value": "invalid"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "comfortable_words.sentences",
            "option_value": "not-json",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "prayers.adversity.especially_clause",
            "option_value": "invalid",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "prayers.adversity.especially_names",
            "option_value": "x" * 1000,
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "prayers.saints.named_insert",
            "option_value": "omit",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "prayers.saints.named_person",
            "option_value": "St. Mary",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "prayers.ast.profile",
            "option_value": "invalid",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "prayers.ast.civil_leader.title",
            "option_value": "invalid",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "prayers.ast.civil_leader.name",
            "option_value": "Jane Doe",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "prayers.form", "option_value": "invalid"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "post_communion.form", "option_value": "invalid"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "fraction.form", "option_value": "invalid"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "communion.invitation.form", "option_value": "invalid"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "communion.invitation.appended_clause",
            "option_value": "invalid",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "communion.invitation.appended_text",
            "option_value": "x" * 321,
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "communion.distribution.body_clause",
            "option_value": "invalid",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "communion.distribution.body_text",
            "option_value": "x" * 501,
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "communion.distribution.blood_clause",
            "option_value": "invalid",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={
            "option_key": "communion.distribution.blood_text",
            "option_value": "x" * 501,
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]

    response = client.post(
        f"/service/{service_id}/service-option",
        data={"option_key": "confession.invitation_form", "option_value": "short"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid option value" in payload["error"]


def test_service_options_route_rejects_invalid_payload(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=324,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.post(
        f"/service/{service_id}/service-options",
        json={"option_values": ["not-a-dict"]},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid options payload" in payload["error"]


def test_service_option_preview_route_rejects_invalid_payload(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=325,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.post(
        f"/service/{service_id}/service-option-preview",
        json={"row_token": "", "option_values": {}},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Invalid row token" in payload["error"]


def test_service_page_includes_service_option_action(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=286,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
    )
    response = client.get(f"/service/{service_id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Set options" in html
    assert "Live preview" in html
    assert "Use canonical alternate" in html
    assert "plan-row-add-button" in html
    assert "data-custom-add" in html
    assert "Quick add additional prayer" not in html
    assert "Quick add communion sentence" not in html
    assert "Quick add alternate blessing" not in html
    assert "Penitential Acclamation (Kyrie / Trisagion)" in html
    assert "plan-row-penitential-hidden" in html
    assert 'data-service-option-key="comfortable_words.sentences"' in html
    assert 'data-service-option-key="law.form"' in html
    assert 'data-service-option-key="penitential_song.mode"' in html
    assert 'data-service-option-key="psalm.gloria_patri"' in html
    assert 'data-service-option-key="prayers.form"' in html
    assert 'data-service-option-key="post_communion.form"' in html
    assert "/service/286/service-options" in html
    assert "/service/286/service-option-preview" in html


def test_text_uses_lords_prayer_form_option(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=281,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={"lords_prayer.form": "contemporary"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Save us from the time of trial," in html
    assert "who art in heaven," not in html


def test_text_uses_summary_of_law_form_option(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=327,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={"law.form": "decalogue"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Then follows the Decalogue (page 100)." in html
    assert (
        "God spoke these words and said: I am the Lord your God. You shall have no other gods but me."
        in html
    )
    assert "You shall have no other gods but me." in html
    assert "and write all these, your laws, in our hearts, we beseech you." in html
    assert "Hear what our Lord Jesus Christ says:" not in html


def test_text_uses_ast_summary_of_law_form_option(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=336,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
        service_option_values={"law.form": "decalogue"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Then follows the Decalogue (page 100)." in html
    assert (
        "God spoke these words and said: I am the Lord your God. You shall have no other gods but me."
        in html
    )
    assert "You shall not make for yourself any idol." in html
    assert "Hear what our Lord Jesus Christ says:" not in html


def test_text_defaults_to_kyrie_penitential_mode(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=334,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "The Kyrie" in html
    assert "Lord, have mercy upon us." in html
    assert "The Trisagion" not in html
    assert "Holy God," not in html


def test_text_uses_penitential_song_and_kyrie_form_options(
    auth_client, service_factory
):
    client, user_id = auth_client
    kyrie_service_id = service_factory(
        user_id=user_id,
        service_id=328,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={
            "penitential_song.mode": "kyrie",
            "kyrie.form": "greek",
        },
    )
    kyrie_response = client.get(f"/service/{kyrie_service_id}/view")
    assert kyrie_response.status_code == 200
    kyrie_html = kyrie_response.get_data(as_text=True)
    assert "Kyrie eleison." in kyrie_html
    assert "Lord, have mercy upon us." not in kyrie_html
    assert "Lord, have mercy." not in kyrie_html
    assert "Holy God," not in kyrie_html
    assert "*or this*" not in kyrie_html

    trisagion_service_id = service_factory(
        user_id=user_id,
        service_id=329,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={"penitential_song.mode": "trisagion"},
    )
    trisagion_response = client.get(f"/service/{trisagion_service_id}/view")
    assert trisagion_response.status_code == 200
    trisagion_html = trisagion_response.get_data(as_text=True)
    assert "Holy God," in trisagion_html
    assert "Lord, have mercy upon us." not in trisagion_html


def test_text_uses_ast_confession_invitation_form_option(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=282,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
        service_option_values={"confession.invitation_form": "short"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Let us humbly confess our sins to Almighty God." in html
    assert "All who truly and earnestly repent of your sins" not in html


def test_text_uses_dismissal_form_option(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=283,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={"dismissal.form": "let_us_bless"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Let us bless the Lord." in html
    assert "Go in peace to love and serve the Lord." not in html
    assert (
        "Let us go forth into the world, rejoicing in the power of the Holy Spirit."
        not in html
    )
    assert "From the Easter Vigil through the Day of Pentecost" not in html
    assert "*The People respond*" not in html


def test_text_uses_fraction_form_option(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=296,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={"fraction.form": "passover_lamb_has_been_sacrificed"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert (
        "Christ our Passover Lamb has been sacrificed, once for all upon the Cross."
        in html
    )
    assert "Christ our Passover is sacrificed for us." not in html
    assert "*or this*" not in html


def test_text_uses_filioque_clause_omit_option(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=301,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={"creed.filioque_clause": "omit"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "who proceeds from the Father [and the Son]," not in html
    assert "who proceeds from the Father and the Son," not in html
    assert "who proceeds from the Father," in html


def test_text_uses_filioque_clause_include_option(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=302,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={"creed.filioque_clause": "include"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "who proceeds from the Father [and the Son]," not in html
    assert "who proceeds from the Father and the Son," in html


def test_text_uses_comfortable_words_sentences_selection(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=318,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={
            "comfortable_words.sentences": [
                "matthew_11_28",
                "first_timothy_1_15",
            ]
        },
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Come to me, all who labor and are heavy laden" in html
    assert "The saying is trustworthy and deserving of full acceptance" in html
    assert "God so loved the world, that he gave his only-begotten Son" not in html
    assert (
        "If anyone sins, we have an advocate with the Father, Jesus Christ the righteous."
        not in html
    )


def test_text_uses_rat_prayers_clause_omit_options(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=304,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={
            "prayers.public_service.especially_clause": "omit",
            "prayers.adversity.especially_clause": "omit",
            "prayers.departed.especially_clause": "omit",
        },
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "for all in public service [especially" not in html
    assert "any other adversity [especially" not in html
    assert "resurrection, [especially" not in html
    assert "for all in public service." in html
    assert "any other adversity." in html
    assert "resurrection, in thanksgiving let us pray." in html


def test_text_uses_prayers_named_fill_values(auth_client, service_factory):
    client, user_id = auth_client
    rat_service_id = service_factory(
        user_id=user_id,
        service_id=308,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={
            "prayers.public_service.especially_names": "our mayor and city council",
            "prayers.adversity.especially_names": "the sick and homebound",
            "prayers.departed.especially_names": "Jane Doe",
        },
    )
    rat_response = client.get(f"/service/{rat_service_id}/view")
    assert rat_response.status_code == 200
    rat_html = rat_response.get_data(as_text=True)
    assert "public service especially our mayor and city council." in rat_html
    assert "any other adversity especially the sick and homebound." in rat_html
    assert "resurrection, especially Jane Doe, in thanksgiving let us pray." in rat_html

    ast_service_id = service_factory(
        user_id=user_id,
        service_id=309,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
        service_option_values={
            "prayers.adversity.especially_names": "those undergoing treatment",
            "prayers.departed.especially_names": "Richard Roe",
            "prayers.saints.named_person": "St. Mary",
        },
    )
    ast_response = client.get(f"/service/{ast_service_id}/view")
    assert ast_response.status_code == 200
    ast_html = ast_response.get_data(as_text=True)
    assert "any other adversity especially those undergoing treatment." in ast_html
    assert (
        "faith and fear, especially Richard Roe, that your will for them may be fulfilled;"
        in ast_html
    )
    assert "good examples of St. Mary, and all your saints" in ast_html


def test_text_uses_ast_prayers_profile_substitutions(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=311,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
        service_option_values={
            "prayers.ast.civil_leader.name": "Jane Doe",
            "prayers.ast.civil_leader.title": "prime_minister",
            "prayers.ast.clergy.name": "Bp. John",
            "prayers.ast.clergy.title": "bishop",
        },
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "especially Jane Doe, our Prime Minister," in html
    assert "especially to your servant(s) Bp. John, our Bishop, etc.," in html
    assert "President/Sovereign/Prime Minister" not in html
    assert "Archbishop/Bishop/Priest/Deacon, etc." not in html


def test_text_ast_prayers_profile_defaults_to_american(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=312,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "especially N, our President," in html
    assert "servant(s) N, our Bishop, etc.," in html
    assert "President/Sovereign/Prime Minister" not in html
    assert "Archbishop/Bishop/Priest/Deacon, etc." not in html


def test_text_ast_prayers_profile_commonwealth_defaults(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=313,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
        service_option_values={"prayers.ast.profile": "commonwealth"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "especially N, our Sovereign," in html
    assert "servant(s) N, our Archbishop, etc.," in html
    assert "President/Sovereign/Prime Minister" not in html
    assert "Archbishop/Bishop/Priest/Deacon, etc." not in html


def test_text_cross_rite_swap_uses_ast_prayers_and_post_communion(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=315,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={
            "prayers.form": "ast",
            "post_communion.form": "other_rite",
        },
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert (
        "Almighty and everliving God, we are taught by your holy Word to offer prayers and supplications"
        in html
    )
    assert (
        "Let us pray for the Church and for the world, saying, “hear our prayer.”"
        not in html
    )
    assert "that we are true members of the mystical body of your Son" in html
    assert "send us out to do the work you have given us to do" not in html


def test_text_cross_rite_swap_uses_rat_prayers_and_post_communion(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=316,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
        service_option_values={
            "prayers.form": "rat",
            "post_communion.form": "other_rite",
        },
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert (
        "Let us pray for the Church and for the world, saying, “hear our prayer.”"
        in html
    )
    assert (
        "Almighty and everliving God, we are taught by your holy Word to offer prayers and supplications"
        not in html
    )
    assert "send us out to do the work you have given us to do" in html
    assert "that we are true members of the mystical body of your Son" not in html


def test_text_uses_ast_prayers_clause_omit_and_include_options(
    auth_client, service_factory
):
    client, user_id = auth_client
    omit_service_id = service_factory(
        user_id=user_id,
        service_id=305,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
        service_option_values={
            "prayers.adversity.especially_clause": "omit",
            "prayers.departed.especially_clause": "omit",
            "prayers.saints.named_insert": "omit",
        },
    )
    omit_response = client.get(f"/service/{omit_service_id}/view")
    assert omit_response.status_code == 200
    omit_html = omit_response.get_data(as_text=True)
    assert "any other adversity [especially" not in omit_html
    assert "faith and fear, [especially" not in omit_html
    assert "good examples of [N., and] all your saints" not in omit_html
    assert "any other adversity." in omit_html
    assert "faith and fear, that your will for them may be fulfilled;" in omit_html
    assert "good examples of all your saints" in omit_html

    include_service_id = service_factory(
        user_id=user_id,
        service_id=306,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
        service_option_values={"prayers.saints.named_insert": "include"},
    )
    include_response = client.get(f"/service/{include_service_id}/view")
    assert include_response.status_code == 200
    include_html = include_response.get_data(as_text=True)
    assert "good examples of [N., and] all your saints" not in include_html
    assert "good examples of N., and all your saints" in include_html


def test_text_uses_communion_invitation_form_option(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=297,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={"communion.invitation.form": "behold_lamb"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert (
        "Behold the Lamb of God, behold him who takes away the sins of the world."
        in html
    )
    assert "The gifts of God for the people of God." not in html
    assert "*or this*" not in html


def test_text_communion_clause_options_omit_bracketed_text(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=298,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={
            "communion.invitation.form": "gifts_of_god",
            "communion.invitation.appended_clause": "omit",
            "communion.distribution.body_clause": "omit",
            "communion.distribution.blood_clause": "omit",
        },
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "The gifts of God for the people of God." in html
    assert (
        "Take them in remembrance that Christ died for you and feed on him in your hearts by faith, with thanksgiving."
        not in html
    )
    assert (
        "which was given for you, preserve your body and soul to everlasting life."
        not in html
    )
    assert (
        "which was shed for you, preserve your body and soul to everlasting life."
        not in html
    )


def test_text_communion_clause_options_include_unbracketed_text(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=299,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={
            "communion.invitation.form": "gifts_of_god",
            "communion.invitation.appended_clause": "include",
            "communion.distribution.body_clause": "include",
            "communion.distribution.blood_clause": "include",
        },
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert (
        "The gifts of God for the people of God. Take them in remembrance that Christ died for you and feed on him in your hearts by faith, with thanksgiving."
        in html
    )
    assert (
        "The Body of our Lord Jesus Christ, which was given for you, preserve your body and soul to everlasting life. Take and eat this in remembrance that Christ died for you, and feed on him in your heart by faith, with thanksgiving."
        in html
    )
    assert (
        "The Blood of our Lord Jesus Christ, which was shed for you, preserve your body and soul to everlasting life. Drink this in remembrance that Christ’s Blood was shed for you, and be thankful."
        in html
    )
    assert "[Take them in remembrance that Christ died for you" not in html
    assert (
        "[which was given for you, preserve your body and soul to everlasting life."
        not in html
    )
    assert (
        "[which was shed for you, preserve your body and soul to everlasting life."
        not in html
    )


def test_text_communion_clause_custom_text_auto_includes_and_replaces_defaults(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=310,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={
            "communion.invitation.form": "gifts_of_god",
            "communion.invitation.appended_text": "Receive this holy Sacrament in thankful remembrance.",
            "communion.distribution.body_text": "which is given for you, keep you in eternal life.",
            "communion.distribution.blood_text": "which is shed for you, guard you in eternal life.",
        },
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert (
        "The gifts of God for the people of God. Receive this holy Sacrament in thankful remembrance."
        in html
    )
    assert (
        "The Body of our Lord Jesus Christ, which is given for you, keep you in eternal life."
        in html
    )
    assert (
        "The Blood of our Lord Jesus Christ, which is shed for you, guard you in eternal life."
        in html
    )
    assert (
        "Take them in remembrance that Christ died for you and feed on him in your hearts by faith, with thanksgiving."
        not in html
    )
    assert (
        "which was given for you, preserve your body and soul to everlasting life."
        not in html
    )
    assert (
        "which was shed for you, preserve your body and soul to everlasting life."
        not in html
    )
    assert "[Take them in remembrance that Christ died for you" not in html


def test_text_communion_clause_omit_mode_takes_precedence_over_custom_text(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=311,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={
            "communion.invitation.form": "gifts_of_god",
            "communion.invitation.appended_clause": "omit",
            "communion.invitation.appended_text": "Custom invitation text that should not render.",
            "communion.distribution.body_clause": "omit",
            "communion.distribution.body_text": "Custom body text that should not render.",
            "communion.distribution.blood_clause": "omit",
            "communion.distribution.blood_text": "Custom blood text that should not render.",
        },
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "The gifts of God for the people of God." in html
    assert "Custom invitation text that should not render." not in html
    assert "Custom body text that should not render." not in html
    assert "Custom blood text that should not render." not in html
    assert (
        "Take them in remembrance that Christ died for you and feed on him in your hearts by faith, with thanksgiving."
        not in html
    )
    assert (
        "which was given for you, preserve your body and soul to everlasting life."
        not in html
    )
    assert (
        "which was shed for you, preserve your body and soul to everlasting life."
        not in html
    )


def test_text_psalm_gloria_patri_option_omit(auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=330,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={"psalm.gloria_patri": "omit"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "At the end of the psalm the Gloria Patri" not in html
    assert "Glory be to the Father, and to the Son, and to the Holy Spirit" not in html


def test_text_fraction_alleluia_mode_off_omits_bracketed_tokens(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=288,
        service_date="2026-03-01",
        season="Lent",
        rite="Renewed Ancient Text",
        service_option_values={"fraction.alleluia_mode": "off"},
    )
    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "[Alleluia.]" not in html
    assert "Christ our Passover is sacrificed for us." in html
    assert (
        re.search(
            r"Christ our Passover is sacrificed for us\.</span><br\s*/?>\s*\n<em>People</em>",
            html,
        )
        is not None
    )
    assert "Therefore let us keep the feast." in html
    assert (
        "In Lent, Alleluia is omitted, and may be omitted at other times except during Easter Season."
        not in html
    )


def test_text_fraction_alleluia_mode_auto_and_on_enable_tokens(
    auth_client, service_factory
):
    client, user_id = auth_client
    auto_service_id = service_factory(
        user_id=user_id,
        service_id=289,
        service_date="2026-04-12",
        season="Easter",
        rite="Renewed Ancient Text",
        service_option_values={"fraction.alleluia_mode": "auto"},
    )
    auto_response = client.get(f"/service/{auto_service_id}/view")
    assert auto_response.status_code == 200
    auto_html = auto_response.get_data(as_text=True)
    assert "Alleluia. Christ our Passover is sacrificed for us." in auto_html
    assert "Therefore let us keep the feast. Alleluia." in auto_html

    on_service_id = service_factory(
        user_id=user_id,
        service_id=290,
        service_date="2026-03-01",
        season="Lent",
        rite="Renewed Ancient Text",
        service_option_values={"fraction.alleluia_mode": "on"},
    )
    on_response = client.get(f"/service/{on_service_id}/view")
    assert on_response.status_code == 200
    on_html = on_response.get_data(as_text=True)
    assert "Alleluia. Christ our Passover is sacrificed for us." in on_html
    assert "Therefore let us keep the feast. Alleluia." in on_html


def test_text_dismissal_alleluia_mode_on_and_off(auth_client, service_factory):
    client, user_id = auth_client
    on_service_id = service_factory(
        user_id=user_id,
        service_id=291,
        service_date="2026-03-01",
        season="Lent",
        rite="Renewed Ancient Text",
        service_option_values={"dismissal.alleluia_mode": "on"},
    )
    on_response = client.get(f"/service/{on_service_id}/view")
    assert on_response.status_code == 200
    on_html = on_response.get_data(as_text=True)
    assert "Let us go forth in the Name of Christ. Alleluia, alleluia." in on_html
    assert "Thanks be to God. Alleluia, alleluia." in on_html
    assert "From the Easter Vigil through the Day of Pentecost" not in on_html

    off_service_id = service_factory(
        user_id=user_id,
        service_id=292,
        service_date="2026-04-12",
        season="Easter",
        rite="Renewed Ancient Text",
        service_option_values={"dismissal.alleluia_mode": "off"},
    )
    off_response = client.get(f"/service/{off_service_id}/view")
    assert off_response.status_code == 200
    off_html = off_response.get_data(as_text=True)
    assert "Let us go forth in the Name of Christ. Alleluia, alleluia." not in off_html
    assert "Thanks be to God. Alleluia, alleluia." not in off_html


def test_text_dismissal_alleluia_mode_auto_uses_season(auth_client, service_factory):
    client, user_id = auth_client
    lent_service_id = service_factory(
        user_id=user_id,
        service_id=293,
        service_date="2026-03-01",
        season="Lent",
        rite="Renewed Ancient Text",
        service_option_values={"dismissal.alleluia_mode": "auto"},
    )
    lent_response = client.get(f"/service/{lent_service_id}/view")
    assert lent_response.status_code == 200
    lent_html = lent_response.get_data(as_text=True)
    assert "Let us go forth in the Name of Christ. Alleluia, alleluia." not in lent_html
    assert "Thanks be to God. Alleluia, alleluia." not in lent_html

    easter_service_id = service_factory(
        user_id=user_id,
        service_id=294,
        service_date="2026-04-12",
        season="Easter",
        rite="Renewed Ancient Text",
        service_option_values={"dismissal.alleluia_mode": "auto"},
    )
    easter_response = client.get(f"/service/{easter_service_id}/view")
    assert easter_response.status_code == 200
    easter_html = easter_response.get_data(as_text=True)
    assert "Let us go forth in the Name of Christ. Alleluia, alleluia." in easter_html
    assert "Thanks be to God. Alleluia, alleluia." in easter_html


def test_collect_override_labels_use_friendly_names(app):
    with app.app_context():
        db = get_db()
        advent_collect = db.execute(
            "select id from texts where type=? and filter_type=? and filter_content=? limit 1",
            ("collect", "proper", "AdventI"),
        ).fetchone()
        options = _load_collect_options(db)
    by_id = {option["id"]: option["label"] for option in options}
    assert advent_collect is not None
    assert by_id[advent_collect["id"]].startswith("The First Sunday in Advent:")
    assert any(option["label"].startswith("Proper 1:") for option in options)
    assert any(
        option["label"].startswith("Missionary Evangelist:") for option in options
    )


def test_collect_override_labels_sort_in_church_year_and_natural_order(app):
    with app.app_context():
        db = get_db()
        options = _load_collect_options(db)

    labels = [option["label"] for option in options]

    def index_of(prefix):
        for idx, label in enumerate(labels):
            if label.startswith(prefix):
                return idx
        raise AssertionError(f"Missing collect option with prefix: {prefix}")

    advent_i = index_of("The First Sunday in Advent:")
    epiphany_i = index_of("The First Sunday of Epiphany:")
    proper_1 = index_of("Proper 1:")
    proper_2 = index_of("Proper 2:")
    proper_10 = index_of("Proper 10:")
    proper_19 = index_of("Proper 19:")

    assert advent_i < epiphany_i
    assert proper_1 < proper_2 < proper_10 < proper_19


def test_custom_element_added_to_service_plan_and_text(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=30,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        text_order=json.dumps([68, 69]),
        text_disabled=json.dumps([]),
    )
    response = client.post(
        f"/service/{service_id}/custom-element",
        data={
            "title": "Custom Blessing",
            "text": "Custom text",
            "rite": "Renewed Ancient Text",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        db = get_db()
        element = db.execute(
            "select id, title, text from service_custom_elements where service_id=? and user_id=? limit 1",
            (service_id, user_id),
        ).fetchone()
        assert element is not None
        assert element["title"] == "Custom Blessing"
        assert element["text"] == "Custom text"
        service = db.execute(
            "select text_order from services where id=? limit 1", (service_id,)
        ).fetchone()
        order_tokens = json.loads(service["text_order"])
        assert order_tokens[:2] == ["text:68", "text:69"]
        assert order_tokens[-1] == f"custom:{element['id']}"

    text_response = client.get(f"/service/{service_id}/view")
    assert text_response.status_code == 200
    assert b"Custom Blessing" in text_response.data
    assert b"Custom text" in text_response.data


def test_custom_element_edit_updates_content(app, auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=31,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        text_order=json.dumps([68, 69]),
        text_disabled=json.dumps([]),
    )
    response = client.post(
        f"/service/{service_id}/custom-element",
        data={
            "title": "Custom Welcome",
            "text": "Original",
            "rite": "Renewed Ancient Text",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        db = get_db()
        element = db.execute(
            "select id from service_custom_elements where service_id=? and user_id=? limit 1",
            (service_id, user_id),
        ).fetchone()
    response = client.post(
        f"/service/{service_id}/custom-element",
        data={
            "custom_id": str(element["id"]),
            "title": "Custom Welcome",
            "text": "Updated",
            "rite": "Renewed Ancient Text",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        db = get_db()
        updated = db.execute(
            "select title, text from service_custom_elements where id=? limit 1",
            (element["id"],),
        ).fetchone()
        assert updated["text"] == "Updated"


def test_custom_element_autosave_edit_returns_json(app, auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=33,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        text_order=json.dumps([68, 69]),
        text_disabled=json.dumps([]),
    )
    response = client.post(
        f"/service/{service_id}/custom-element",
        data={
            "title": "Custom Sending",
            "text": "Original",
            "rite": "Renewed Ancient Text",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        db = get_db()
        element = db.execute(
            "select id from service_custom_elements where service_id=? and user_id=? limit 1",
            (service_id, user_id),
        ).fetchone()
    response = client.post(
        f"/service/{service_id}/custom-element",
        data={
            "custom_id": str(element["id"]),
            "title": "Custom Sending",
            "text": "Updated by autosave",
            "rite": "Renewed Ancient Text",
            "autosave": "1",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["custom_id"] == element["id"]
    with app.app_context():
        db = get_db()
        updated = db.execute(
            "select text from service_custom_elements where id=? limit 1",
            (element["id"],),
        ).fetchone()
        assert updated["text"] == "Updated by autosave"


def test_custom_element_edit_denies_other_user(
    app, auth_client, user_factory, service_factory
):
    client, _ = auth_client
    other_user_id = user_factory(email="other-edit@example.com")
    service_id = service_factory(
        user_id=other_user_id,
        service_id=67,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            "insert into service_custom_elements (service_id, user_id, title, text) values (?, ?, ?, ?)",
            (service_id, other_user_id, "Other", "Other text"),
        )
        db.commit()
        element_id = cursor.lastrowid
    response = client.post(
        f"/service/{service_id}/custom-element",
        data={
            "custom_id": str(element_id),
            "title": "Updated",
            "text": "Updated text",
            "rite": "Renewed Ancient Text",
        },
    )
    assert response.status_code == 404
    with app.app_context():
        db = get_db()
        row = db.execute(
            "select title, text from service_custom_elements where id=? limit 1",
            (element_id,),
        ).fetchone()
        assert row["text"] == "Other text"


def test_custom_element_autosave_missing_title_returns_error(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=34,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    response = client.post(
        f"/service/{service_id}/custom-element",
        data={
            "custom_id": "1",
            "title": "",
            "text": "Updated by autosave",
            "rite": "Renewed Ancient Text",
            "autosave": "1",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Title is required" in payload["error"]


def test_custom_element_delete_removes_from_plan(app, auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=32,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        text_order=json.dumps([68, 69]),
        text_disabled=json.dumps([]),
    )
    response = client.post(
        f"/service/{service_id}/custom-element",
        data={
            "title": "Custom Dismissal",
            "text": "Dismissal",
            "rite": "Renewed Ancient Text",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        db = get_db()
        element = db.execute(
            "select id from service_custom_elements where service_id=? and user_id=? limit 1",
            (service_id, user_id),
        ).fetchone()
    response = client.post(
        f"/service/{service_id}/custom-element/{element['id']}/delete"
    )
    assert response.status_code == 302
    with app.app_context():
        db = get_db()
        deleted = db.execute(
            "select id from service_custom_elements where id=? limit 1",
            (element["id"],),
        ).fetchone()
        assert deleted is None
        service = db.execute(
            "select text_order from services where id=? limit 1", (service_id,)
        ).fetchone()
        order_tokens = json.loads(service["text_order"])
        assert f"custom:{element['id']}" not in order_tokens


def test_custom_element_delete_denies_other_user(
    app, auth_client, user_factory, service_factory
):
    client, _ = auth_client
    other_user_id = user_factory(email="other@example.com")
    service_id = service_factory(
        user_id=other_user_id,
        service_id=66,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            "insert into service_custom_elements (service_id, user_id, title, text) values (?, ?, ?, ?)",
            (service_id, other_user_id, "Other", "Other text"),
        )
        db.commit()
        element_id = cursor.lastrowid
    response = client.post(f"/service/{service_id}/custom-element/{element_id}/delete")
    assert response.status_code == 404
    with app.app_context():
        db = get_db()
        element = db.execute(
            "select id from service_custom_elements where id=? limit 1",
            (element_id,),
        ).fetchone()
        assert element is not None


def test_custom_elements_escape_html_in_text(app, auth_client, service_factory):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=40,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        text_order=json.dumps([]),
        text_disabled=json.dumps([]),
    )
    title = "<script>custom-title</script>"
    text = "<img src=x onerror=alert(1)> **bold**"
    with app.app_context():
        db = get_db()
        db.execute(
            "insert into service_custom_elements (service_id, user_id, title, text) values (?, ?, ?, ?)",
            (service_id, user_id, title, text),
        )
        db.commit()

    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "<script>custom-title</script>" not in body
    assert "&lt;script&gt;custom-title&lt;/script&gt;" in body
    assert "<img src=x onerror=alert(1)>" not in body
    assert "&lt;img src=x onerror=alert(1)&gt;" in body
    assert "<strong>bold</strong>" in body
