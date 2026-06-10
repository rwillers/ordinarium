from ordinarium import pco_sync
from ordinarium.db import get_db


def _payloads(items):
    return pco_sync.build_pco_item_payloads(items)


def _insert_item_link(
    service_id, token, pco_item_id, content_hash="stale", last_position=0
):
    db = get_db()
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
        (service_id, token, pco_item_id, content_hash, last_position),
    )
    db.commit()


def test_list_plan_templates_paginates(monkeypatch):
    calls = []

    def fake_api_request(
        method,
        base_url,
        path,
        access_token,
        json=None,
        params=None,
        absolute_url=False,
    ):
        calls.append((method, base_url, path, access_token, absolute_url))
        if not absolute_url:
            return {
                "data": [{"id": "template-1"}],
                "links": {"next": "https://example.test/next"},
            }
        return {"data": [{"id": "template-2"}], "links": {}}

    monkeypatch.setattr(pco_sync, "api_request", fake_api_request)

    templates = pco_sync.list_plan_templates(
        "https://example.test", "token", "service-type-1"
    )

    assert templates == [{"id": "template-1"}, {"id": "template-2"}]
    assert calls == [
        (
            "GET",
            "https://example.test",
            "/services/v2/service_types/service-type-1/plan_templates",
            "token",
            False,
        ),
        (
            "GET",
            "https://example.test",
            "https://example.test/next",
            "token",
            True,
        ),
    ]


def test_import_plan_template_calls_import_action(monkeypatch):
    calls = []

    def fake_api_request(method, base_url, path, access_token, json=None):
        calls.append((method, base_url, path, access_token, json))
        return {"data": {"id": "imported"}}

    monkeypatch.setattr(pco_sync, "api_request", fake_api_request)

    result = pco_sync.import_plan_template(
        "https://example.test",
        "token",
        "service-type-1",
        "plan-1",
        "template-1",
    )

    assert result == {"data": {"id": "imported"}}
    assert calls == [
        (
            "POST",
            "https://example.test",
            "/services/v2/service_types/service-type-1/plans/plan-1/import_template",
            "token",
            {
                "data": {
                    "attributes": {
                        "plan_id": "template-1",
                        "copy_items": False,
                        "copy_people": True,
                        "copy_notes": True,
                    }
                }
            },
        )
    ]


def test_import_plan_template_sends_numeric_template_id_as_integer(monkeypatch):
    calls = []

    def fake_api_request(method, base_url, path, access_token, json=None):
        calls.append(json)
        return {"data": {"id": "imported"}}

    monkeypatch.setattr(pco_sync, "api_request", fake_api_request)

    pco_sync.import_plan_template(
        "https://example.test",
        "token",
        "service-type-1",
        "plan-1",
        "123",
    )

    assert calls[0]["data"]["attributes"]["plan_id"] == 123


def test_delta_sync_skips_unchanged_linked_items_and_preserves_manual(
    app, service_factory, user_factory, monkeypatch
):
    user_id = user_factory(email="delta-unchanged@example.com")
    service_id = service_factory(user_id=user_id, service_id=801)
    with app.app_context():
        payloads = _payloads(
            [{"token": "text:1", "title": "Collect", "text": "The Lord be with you."}]
        )
        _insert_item_link(
            service_id,
            "text:1",
            "pco-1",
            content_hash=payloads[0]["content_hash"],
        )
        calls = []
        monkeypatch.setattr(
            pco_sync,
            "list_plan_items",
            lambda *_args: [{"id": "pco-1"}, {"id": "manual-1"}],
        )
        monkeypatch.setattr(
            pco_sync, "update_plan_item", lambda *args: calls.append(("patch", args))
        )
        monkeypatch.setattr(
            pco_sync, "create_plan_item", lambda *args: calls.append(("post", args))
        )
        monkeypatch.setattr(
            pco_sync, "delete_plan_item", lambda *args: calls.append(("delete", args))
        )

        pco_sync._sync_pco_item_delta(
            service_id, "base", "token", "type-1", "plan-1", payloads
        )

        assert calls == []


def test_delta_sync_patches_changed_linked_item(
    app, service_factory, user_factory, monkeypatch
):
    user_id = user_factory(email="delta-patch@example.com")
    service_id = service_factory(user_id=user_id, service_id=802)
    with app.app_context():
        payloads = _payloads(
            [{"token": "text:1", "title": "Collect", "text": "Updated text."}]
        )
        _insert_item_link(service_id, "text:1", "pco-1", content_hash="old-hash")
        calls = []
        monkeypatch.setattr(
            pco_sync,
            "list_plan_items",
            lambda *_args: [{"id": "pco-1"}, {"id": "manual-1"}],
        )
        monkeypatch.setattr(
            pco_sync, "update_plan_item", lambda *args: calls.append(args)
        )

        pco_sync._sync_pco_item_delta(
            service_id, "base", "token", "type-1", "plan-1", payloads
        )

        assert len(calls) == 1
        assert calls[0][:5] == ("base", "token", "type-1", "plan-1", "pco-1")
        assert calls[0][5] == payloads[0]["payload"]
        row = (
            get_db()
            .execute(
                "select last_content_hash from service_pco_item_links where service_id=?",
                (service_id,),
            )
            .fetchone()
        )
        assert row["last_content_hash"] == payloads[0]["content_hash"]


def test_delta_sync_creates_new_item_and_stores_link(
    app, service_factory, user_factory, monkeypatch
):
    user_id = user_factory(email="delta-create@example.com")
    service_id = service_factory(user_id=user_id, service_id=803)
    with app.app_context():
        payloads = _payloads(
            [{"token": "text:1", "title": "Collect", "text": "Created text."}]
        )
        calls = []
        monkeypatch.setattr(pco_sync, "list_plan_items", lambda *_args: [])

        def fake_create(*args):
            calls.append(args)
            return {"data": {"id": "created-1"}}

        monkeypatch.setattr(pco_sync, "create_plan_item", fake_create)

        pco_sync._sync_pco_item_delta(
            service_id, "base", "token", "type-1", "plan-1", payloads
        )

        assert calls[0][4] == payloads[0]["payload"]
        row = (
            get_db()
            .execute(
                """
            select ordinarium_token, pco_item_id, last_content_hash, last_position
            from service_pco_item_links
            where service_id=?
            """,
                (service_id,),
            )
            .fetchone()
        )
        assert row["ordinarium_token"] == "text:1"
        assert row["pco_item_id"] == "created-1"
        assert row["last_content_hash"] == payloads[0]["content_hash"]
        assert row["last_position"] == 0


def test_delta_sync_deletes_removed_owned_item_only(
    app, service_factory, user_factory, monkeypatch
):
    user_id = user_factory(email="delta-delete@example.com")
    service_id = service_factory(user_id=user_id, service_id=804)
    with app.app_context():
        _insert_item_link(service_id, "text:1", "pco-1")
        deleted = []
        monkeypatch.setattr(
            pco_sync,
            "list_plan_items",
            lambda *_args: [{"id": "pco-1"}, {"id": "manual-1"}],
        )
        monkeypatch.setattr(
            pco_sync, "delete_plan_item", lambda *args: deleted.append(args)
        )

        pco_sync._sync_pco_item_delta(
            service_id, "base", "token", "type-1", "plan-1", []
        )

        assert [call[4] for call in deleted] == ["pco-1"]
        remaining = (
            get_db()
            .execute(
                "select count(*) from service_pco_item_links where service_id=?",
                (service_id,),
            )
            .fetchone()[0]
        )
        assert remaining == 0


def test_delta_sync_rebuilds_owned_items_when_order_changes(
    app, service_factory, user_factory, monkeypatch
):
    user_id = user_factory(email="delta-reorder@example.com")
    service_id = service_factory(user_id=user_id, service_id=805)
    with app.app_context():
        _insert_item_link(service_id, "text:a", "pco-a", last_position=0)
        _insert_item_link(service_id, "text:b", "pco-b", last_position=1)
        payloads = _payloads(
            [
                {"token": "text:b", "title": "Second", "text": "B"},
                {"token": "text:a", "title": "First", "text": "A"},
            ]
        )
        deleted = []
        created = []
        monkeypatch.setattr(
            pco_sync,
            "list_plan_items",
            lambda *_args: [{"id": "pco-a"}, {"id": "pco-b"}, {"id": "manual-1"}],
        )
        monkeypatch.setattr(
            pco_sync, "delete_plan_item", lambda *args: deleted.append(args)
        )

        def fake_create(*args):
            created.append(args)
            return {"data": {"id": f"created-{len(created)}"}}

        monkeypatch.setattr(pco_sync, "create_plan_item", fake_create)

        pco_sync._sync_pco_item_delta(
            service_id, "base", "token", "type-1", "plan-1", payloads
        )

        assert [call[4] for call in deleted] == ["pco-a", "pco-b"]
        assert [call[4]["data"]["attributes"]["title"] for call in created] == [
            "Second",
            "First",
        ]
        rows = (
            get_db()
            .execute(
                """
            select ordinarium_token, pco_item_id, last_position
            from service_pco_item_links
            where service_id=?
            order by last_position
            """,
                (service_id,),
            )
            .fetchall()
        )
        assert [(row["ordinarium_token"], row["pco_item_id"]) for row in rows] == [
            ("text:b", "created-1"),
            ("text:a", "created-2"),
        ]
