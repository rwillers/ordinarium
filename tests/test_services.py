import json
from datetime import date, timedelta

import ordinarium.text_routes as text_routes
from ordinarium.db import get_db
from ordinarium.liturgical_calendar import resolve_observance, resolve_season


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
        db.execute(
            "insert into service_custom_elements (service_id, user_id, title, text) values (?, ?, ?, ?)",
            (source_id, user_id, "Custom Blessing", "Custom text"),
        )
        element = db.execute(
            "select id from service_custom_elements where service_id=? and user_id=? limit 1",
            (source_id, user_id),
        ).fetchone()
        db.execute(
            "update services set text_order=?, text_disabled=? where id=?",
            (
                json.dumps(["text:68", f"custom:{element['id']}", "text:69"]),
                json.dumps([f"custom:{element['id']}"]),
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
                   text_order, text_disabled
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
