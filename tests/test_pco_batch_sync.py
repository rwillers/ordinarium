import time

from ordinarium.db import get_db
from ordinarium.pco_client import PcoApiError


def _enable_pco_feature(app, user_id):
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


def _post_batch_sync_and_wait(client, payload):
    response = client.post(
        "/services/pco/batch-sync",
        json=payload,
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 202
    queued = response.get_json()
    assert queued["ok"] is True
    assert queued["job_id"]
    assert queued["status_url"]
    for _attempt in range(100):
        status_response = client.get(
            queued["status_url"], headers={"Accept": "application/json"}
        )
        assert status_response.status_code == 200
        status_payload = status_response.get_json()
        if status_payload["status"] in {"succeeded", "failed"}:
            return queued, status_payload
        time.sleep(0.02)
    raise AssertionError("PCO batch sync job did not finish.")


def test_services_pco_batch_sync_enforces_limit(app, auth_client):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    rows = [{"service_id": index + 1, "mode": "skip"} for index in range(26)]
    response = client.post(
        "/services/pco/batch-sync",
        json={"rows": rows, "pco_plan_time": "10:00", "pco_plan_tz_offset": "0"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "up to 25 services" in payload["error"]


def test_services_pco_batch_sync_handles_mixed_modes(
    app, auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(user_id=user_id, service_id=301, service_date="2099-01-04")
    service_factory(
        user_id=user_id,
        service_id=302,
        service_date="2099-01-11",
        title="Second Sunday",
    )
    service_factory(user_id=user_id, service_id=303, service_date="2099-01-18")
    with app.app_context():
        db = get_db()
        db.execute(
            """
            insert into service_pco_links (
              service_id,
              pco_service_type_id,
              pco_service_type_name,
              pco_plan_id,
              pco_plan_title
            ) values (?, ?, ?, ?, ?)
            """,
            (301, "type-linked", "Linked type", "plan-linked", "Linked Plan"),
        )
        db.execute(
            """
            insert into service_pco_links (
              service_id,
              pco_service_type_id,
              pco_service_type_name,
              pco_plan_id,
              pco_plan_title
            ) values (?, ?, ?, ?, ?)
            """,
            (303, "type-old", "Old type", "plan-old", "Old Plan"),
        )
        db.commit()

    created_titles = {}
    sync_calls = []

    def fake_create_plan(
        _base_url, _access_token, _service_type_id, title, _plan_date, _series_title
    ):
        plan_id = f"created-{title.replace(' ', '-').lower()}"
        created_titles[plan_id] = title
        return {"data": {"id": plan_id, "attributes": {"title": f"{title} (PCO)"}}}

    def fake_create_plan_time(
        _base_url,
        _access_token,
        _service_type_id,
        _plan_id,
        _plan_date,
        _plan_time,
        _tz_offset_minutes,
    ):
        return None

    def fake_fetch_plan(_base_url, _access_token, _service_type_id, plan_id):
        return {"data": {"id": plan_id, "attributes": {"title": "Overridden plan"}}}

    def fake_sync_service_plan(
        service_id,
        _user_id,
        _access_token,
        _base_url,
        service_type_id,
        plan_id,
    ):
        sync_calls.append((service_id, service_type_id, plan_id))
        return {"synced_at": "2099-01-01T10:00:00", "item_count": 1}

    monkeypatch.setattr("ordinarium.service_pco_routes.create_plan", fake_create_plan)
    monkeypatch.setattr(
        "ordinarium.service_pco_routes.create_plan_time", fake_create_plan_time
    )
    monkeypatch.setattr("ordinarium.service_pco_routes.fetch_plan", fake_fetch_plan)
    monkeypatch.setattr(
        "ordinarium.service_pco_routes.sync_service_plan", fake_sync_service_plan
    )

    _queued, payload = _post_batch_sync_and_wait(
        client,
        {
            "rows": [
                {"service_id": 301, "mode": "sync_linked"},
                {
                    "service_id": 302,
                    "mode": "create_new",
                    "pco_service_type_id": "type-created",
                    "pco_service_type_name": "Created type",
                },
                {
                    "service_id": 303,
                    "mode": "link_existing",
                    "pco_service_type_id": "type-override",
                    "pco_service_type_name": "Override type",
                    "pco_plan_id": "plan-override",
                },
            ],
            "pco_plan_time": "10:00",
            "pco_plan_tz_offset": "0",
        },
    )
    assert payload["ok"] is True
    assert payload["status"] == "succeeded"
    assert payload["summary"] == {"total": 3, "success": 3, "failed": 0, "skipped": 0}
    statuses = [row["status"] for row in payload["results"]]
    assert statuses == ["success", "success", "success"]
    assert (301, "type-linked", "plan-linked") in sync_calls
    assert (303, "type-override", "plan-override") in sync_calls
    with app.app_context():
        db = get_db()
        links = db.execute(
            """
            select service_id, pco_service_type_id, pco_plan_id, last_sync_status
            from service_pco_links
            where service_id in (301, 302, 303)
            order by service_id
            """
        ).fetchall()
        link_map = {row["service_id"]: row for row in links}
        assert link_map[301]["pco_plan_id"] == "plan-linked"
        assert link_map[301]["last_sync_status"] == "success"
        assert link_map[302]["pco_service_type_id"] == "type-created"
        assert link_map[302]["pco_plan_id"] in created_titles
        assert link_map[302]["last_sync_status"] == "success"
        assert link_map[303]["pco_plan_id"] == "plan-override"
        assert link_map[303]["last_sync_status"] == "success"


def test_services_pco_batch_sync_rejects_duplicate_plan_targets(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(user_id=user_id, service_id=401, service_date="2099-02-01")
    service_factory(user_id=user_id, service_id=402, service_date="2099-02-08")
    _queued, payload = _post_batch_sync_and_wait(
        client,
        {
            "rows": [
                {
                    "service_id": 401,
                    "mode": "link_existing",
                    "pco_service_type_id": "dup-type",
                    "pco_plan_id": "dup-plan",
                },
                {
                    "service_id": 402,
                    "mode": "link_existing",
                    "pco_service_type_id": "dup-type",
                    "pco_plan_id": "dup-plan",
                },
            ],
            "pco_plan_time": "10:00",
            "pco_plan_tz_offset": "0",
        },
    )
    assert payload["ok"] is True
    assert payload["status"] == "succeeded"
    assert payload["summary"] == {"total": 2, "success": 0, "failed": 2, "skipped": 0}
    for row in payload["results"]:
        assert row["status"] == "failed"
        assert "same Planning Center plan" in row["error"]


def test_services_pco_batch_sync_limits_to_upcoming(app, auth_client, service_factory):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(user_id=user_id, service_id=501, service_date="2000-01-01")
    _queued, payload = _post_batch_sync_and_wait(
        client,
        {
            "rows": [
                {
                    "service_id": 501,
                    "mode": "create_new",
                    "pco_service_type_id": "type-created",
                }
            ],
            "pco_plan_time": "10:00",
            "pco_plan_tz_offset": "0",
        },
    )
    assert payload["ok"] is True
    assert payload["status"] == "succeeded"
    assert payload["summary"] == {"total": 1, "success": 0, "failed": 1, "skipped": 0}
    assert payload["results"][0]["status"] == "failed"
    assert "not upcoming" in payload["results"][0]["error"]


def test_services_pco_batch_sync_create_new_imports_selected_template(
    app, auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(
        user_id=user_id,
        service_id=701,
        service_date="2099-04-01",
        title="Template service",
    )
    calls = []

    def fake_create_plan(
        _base_url, _access_token, service_type_id, title, _plan_date, _series_title
    ):
        calls.append(("create_plan", service_type_id, title))
        return {"data": {"id": "created-template-plan", "attributes": {"title": title}}}

    def fake_create_plan_time(*_args):
        calls.append(("create_plan_time", _args[3]))

    def fake_import_plan_template(
        _base_url, _access_token, service_type_id, plan_id, template_id
    ):
        calls.append(("import_plan_template", service_type_id, plan_id, template_id))

    def fake_sync_service_plan(
        service_id,
        _user_id,
        _access_token,
        _base_url,
        service_type_id,
        plan_id,
    ):
        calls.append(("sync_service_plan", service_id, service_type_id, plan_id))
        return {"synced_at": "2099-04-01T10:00:00", "item_count": 1}

    monkeypatch.setattr("ordinarium.service_pco_routes.create_plan", fake_create_plan)
    monkeypatch.setattr(
        "ordinarium.service_pco_routes.create_plan_time", fake_create_plan_time
    )
    monkeypatch.setattr(
        "ordinarium.service_pco_routes.import_plan_template",
        fake_import_plan_template,
    )
    monkeypatch.setattr(
        "ordinarium.service_pco_routes.sync_service_plan", fake_sync_service_plan
    )

    _queued, payload = _post_batch_sync_and_wait(
        client,
        {
            "rows": [
                {
                    "service_id": 701,
                    "mode": "create_new",
                    "pco_service_type_id": "type-created",
                    "pco_service_type_name": "Created type",
                    "pco_plan_template_id": "template-1",
                }
            ],
            "pco_plan_time": "10:00",
            "pco_plan_tz_offset": "0",
        },
    )

    assert payload["ok"] is True
    assert payload["summary"] == {"total": 1, "success": 1, "failed": 0, "skipped": 0}
    assert payload["results"][0]["status"] == "success"
    assert calls == [
        ("create_plan", "type-created", "Template service"),
        ("create_plan_time", "created-template-plan"),
        (
            "import_plan_template",
            "type-created",
            "created-template-plan",
            "template-1",
        ),
        ("sync_service_plan", 701, "type-created", "created-template-plan"),
    ]


def test_services_pco_batch_sync_template_import_failure_does_not_link(
    app, auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(
        user_id=user_id,
        service_id=702,
        service_date="2099-04-08",
        title="Template failure",
    )
    sync_calls = []

    monkeypatch.setattr(
        "ordinarium.service_pco_routes.create_plan",
        lambda *_args: {
            "data": {
                "id": "created-template-failure",
                "attributes": {"title": "Template failure"},
            }
        },
    )
    monkeypatch.setattr(
        "ordinarium.service_pco_routes.create_plan_time",
        lambda *_args: None,
    )

    def fake_import_plan_template(*_args):
        raise PcoApiError("Template import failed.", status_code=400)

    monkeypatch.setattr(
        "ordinarium.service_pco_routes.import_plan_template",
        fake_import_plan_template,
    )
    monkeypatch.setattr(
        "ordinarium.service_pco_routes.sync_service_plan",
        lambda *args: sync_calls.append(args),
    )

    _queued, payload = _post_batch_sync_and_wait(
        client,
        {
            "rows": [
                {
                    "service_id": 702,
                    "mode": "create_new",
                    "pco_service_type_id": "type-created",
                    "pco_plan_template_id": "template-1",
                }
            ],
            "pco_plan_time": "10:00",
            "pco_plan_tz_offset": "0",
        },
    )

    assert payload["ok"] is True
    assert payload["summary"] == {"total": 1, "success": 0, "failed": 1, "skipped": 0}
    assert payload["results"][0]["status"] == "failed"
    assert "Template import failed" in payload["results"][0]["error"]
    assert sync_calls == []
    with app.app_context():
        db = get_db()
        link = db.execute(
            "select service_id from service_pco_links where service_id=?",
            (702,),
        ).fetchone()
        assert link is None


def test_services_page_places_pco_batch_action_in_upcoming_section(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    _enable_pco_feature(app, user_id)
    service_factory(user_id=user_id, service_id=601, service_date="2099-03-01")
    service_factory(user_id=user_id, service_id=602, service_date="2000-03-01")
    response = client.get("/services")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    toggle_index = body.find('id="services-pco-batch-toggle"')
    past_index = body.find("<h3>Past services</h3>")
    assert toggle_index != -1
    assert past_index != -1
    assert toggle_index < past_index
    assert "Apply this service type to all editable rows?" in body
    assert (
        "Apply this template to all editable create-new rows with this service type?"
        in body
    )
    assert "Optional template scaffolding." not in body
    assert 'id="service-pco-batch-service-type"' not in body
    assert 'id="service-pco-batch-apply-type"' not in body
