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


def test_adopt_pco_plan_items_imports_unmatched_as_custom_and_links_matches(
    app, service_factory, user_factory, monkeypatch
):
    user_id = user_factory(email="delta-adopt@example.com")
    service_id = service_factory(
        user_id=user_id,
        service_id=806,
        text_order='["text:1", "text:2"]',
    )
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select * from services where id=? limit 1", (service_id,)
        ).fetchone()
        payloads = _payloads(
            [
                {"token": "text:1", "title": "Collect", "text": "Updated text."},
                {"token": "text:2", "title": "Gospel", "text": "The Gospel."},
            ]
        )
        monkeypatch.setattr(
            pco_sync,
            "list_plan_items",
            lambda *_args: [
                {
                    "id": "pco-heading",
                    "attributes": {
                        "title": "Opening Song",
                        "html_details": "<p>All creatures of our God and King</p>",
                    },
                },
                {
                    "id": "pco-collect",
                    "attributes": {
                        "title": "Collect",
                        "html_details": "<p>Old collect text.</p>",
                    },
                },
            ],
        )

        pco_sync._adopt_pco_plan_items(
            service_id,
            user_id,
            service,
            "base",
            "token",
            "type-1",
            "plan-1",
            payloads,
        )

        custom = db.execute(
            """
            select id, title, text
            from service_custom_elements
            where service_id=?
            """,
            (service_id,),
        ).fetchone()
        assert custom["title"] == "Opening Song"
        assert custom["text"] == "<p>All creatures of our God and King</p>"
        custom_token = f"custom:{custom['id']}"
        service_row = db.execute(
            "select text_order from services where id=?", (service_id,)
        ).fetchone()
        assert service_row["text_order"] == (f'["{custom_token}", "text:1", "text:2"]')
        links = db.execute(
            """
            select ordinarium_token, pco_item_id
            from service_pco_item_links
            where service_id=?
            order by last_position
            """,
            (service_id,),
        ).fetchall()
        assert [(row["ordinarium_token"], row["pco_item_id"]) for row in links] == [
            (custom_token, "pco-heading"),
            ("text:1", "pco-collect"),
        ]


def test_adopt_pco_plan_items_preserves_existing_partial_item_link(
    app, service_factory, user_factory, monkeypatch
):
    user_id = user_factory(email="delta-adopt-partial@example.com")
    service_id = service_factory(
        user_id=user_id,
        service_id=808,
        text_order='["text:1"]',
    )
    with app.app_context():
        _insert_item_link(service_id, "text:1", "pco-linked")
        db = get_db()
        service = db.execute(
            "select * from services where id=? limit 1", (service_id,)
        ).fetchone()
        payloads = _payloads(
            [{"token": "text:1", "title": "Collect", "text": "Updated text."}]
        )
        monkeypatch.setattr(
            pco_sync,
            "list_plan_items",
            lambda *_args: [
                {
                    "id": "pco-linked",
                    "attributes": {
                        "title": "Renamed in PCO",
                        "html_details": "<p>Older details.</p>",
                    },
                },
            ],
        )

        pco_sync._adopt_pco_plan_items(
            service_id,
            user_id,
            service,
            "base",
            "token",
            "type-1",
            "plan-1",
            payloads,
        )

        rows = db.execute(
            """
            select ordinarium_token, pco_item_id
            from service_pco_item_links
            where service_id=?
            """,
            (service_id,),
        ).fetchall()
        assert [(row["ordinarium_token"], row["pco_item_id"]) for row in rows] == [
            ("text:1", "pco-linked")
        ]


def test_adopt_pco_plan_items_matches_exact_content_with_duplicate_titles(
    app, service_factory, user_factory, monkeypatch
):
    user_id = user_factory(email="delta-adopt-exact@example.com")
    service_id = service_factory(
        user_id=user_id,
        service_id=809,
        text_order='["text:1"]',
    )
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select * from services where id=? limit 1", (service_id,)
        ).fetchone()
        payloads = _payloads(
            [{"token": "text:1", "title": "Song", "text": "Exact song text."}]
        )
        exact_html = payloads[0]["payload"]["data"]["attributes"]["html_details"]
        monkeypatch.setattr(
            pco_sync,
            "list_plan_items",
            lambda *_args: [
                {
                    "id": "pco-other-song",
                    "attributes": {
                        "title": "Song",
                        "html_details": "<p>Different song text.</p>",
                    },
                },
                {
                    "id": "pco-exact-song",
                    "attributes": {
                        "title": "Song",
                        "html_details": exact_html,
                    },
                },
            ],
        )

        pco_sync._adopt_pco_plan_items(
            service_id,
            user_id,
            service,
            "base",
            "token",
            "type-1",
            "plan-1",
            payloads,
        )

        custom = db.execute(
            """
            select id, title, text
            from service_custom_elements
            where service_id=?
            """,
            (service_id,),
        ).fetchone()
        custom_token = f"custom:{custom['id']}"
        assert custom["title"] == "Song"
        assert custom["text"] == "<p>Different song text.</p>"
        links = db.execute(
            """
            select ordinarium_token, pco_item_id
            from service_pco_item_links
            where service_id=?
            order by last_position
            """,
            (service_id,),
        ).fetchall()
        assert [(row["ordinarium_token"], row["pco_item_id"]) for row in links] == [
            (custom_token, "pco-other-song"),
            ("text:1", "pco-exact-song"),
        ]


def test_adopt_pco_plan_items_does_not_title_match_ambiguous_pco_items(
    app, service_factory, user_factory, monkeypatch
):
    user_id = user_factory(email="delta-adopt-pco-ambiguous@example.com")
    service_id = service_factory(
        user_id=user_id,
        service_id=810,
        text_order='["text:1"]',
    )
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select * from services where id=? limit 1", (service_id,)
        ).fetchone()
        payloads = _payloads(
            [{"token": "text:1", "title": "Song", "text": "Ordinarium text."}]
        )
        monkeypatch.setattr(
            pco_sync,
            "list_plan_items",
            lambda *_args: [
                {
                    "id": "pco-song-1",
                    "attributes": {
                        "title": "Song",
                        "html_details": "<p>First PCO text.</p>",
                    },
                },
                {
                    "id": "pco-song-2",
                    "attributes": {
                        "title": "Song",
                        "html_details": "<p>Second PCO text.</p>",
                    },
                },
            ],
        )

        pco_sync._adopt_pco_plan_items(
            service_id,
            user_id,
            service,
            "base",
            "token",
            "type-1",
            "plan-1",
            payloads,
        )

        custom_rows = db.execute(
            """
            select id, title
            from service_custom_elements
            where service_id=?
            order by id
            """,
            (service_id,),
        ).fetchall()
        custom_tokens = [f"custom:{row['id']}" for row in custom_rows]
        assert [row["title"] for row in custom_rows] == ["Song", "Song"]
        service_row = db.execute(
            "select text_order from services where id=?", (service_id,)
        ).fetchone()
        assert service_row["text_order"] == (
            f'["{custom_tokens[0]}", "{custom_tokens[1]}", "text:1"]'
        )
        links = db.execute(
            """
            select ordinarium_token, pco_item_id
            from service_pco_item_links
            where service_id=?
            order by last_position
            """,
            (service_id,),
        ).fetchall()
        assert [(row["ordinarium_token"], row["pco_item_id"]) for row in links] == [
            (custom_tokens[0], "pco-song-1"),
            (custom_tokens[1], "pco-song-2"),
        ]


def test_adopt_pco_plan_items_does_not_title_match_ambiguous_payloads(
    app, service_factory, user_factory, monkeypatch
):
    user_id = user_factory(email="delta-adopt-payload-ambiguous@example.com")
    service_id = service_factory(
        user_id=user_id,
        service_id=811,
        text_order='["text:1", "text:2"]',
    )
    with app.app_context():
        db = get_db()
        service = db.execute(
            "select * from services where id=? limit 1", (service_id,)
        ).fetchone()
        payloads = _payloads(
            [
                {"token": "text:1", "title": "Song", "text": "First text."},
                {"token": "text:2", "title": "Song", "text": "Second text."},
            ]
        )
        monkeypatch.setattr(
            pco_sync,
            "list_plan_items",
            lambda *_args: [
                {
                    "id": "pco-song",
                    "attributes": {
                        "title": "Song",
                        "html_details": "<p>PCO text.</p>",
                    },
                },
            ],
        )

        pco_sync._adopt_pco_plan_items(
            service_id,
            user_id,
            service,
            "base",
            "token",
            "type-1",
            "plan-1",
            payloads,
        )

        custom = db.execute(
            """
            select id, title
            from service_custom_elements
            where service_id=?
            """,
            (service_id,),
        ).fetchone()
        custom_token = f"custom:{custom['id']}"
        assert custom["title"] == "Song"
        service_row = db.execute(
            "select text_order from services where id=?", (service_id,)
        ).fetchone()
        assert service_row["text_order"] == (f'["{custom_token}", "text:1", "text:2"]')
        links = db.execute(
            """
            select ordinarium_token, pco_item_id
            from service_pco_item_links
            where service_id=?
            """,
            (service_id,),
        ).fetchall()
        assert [(row["ordinarium_token"], row["pco_item_id"]) for row in links] == [
            (custom_token, "pco-song")
        ]


def test_reset_pco_plan_items_deletes_all_existing_and_recreates_owned_items(
    app, service_factory, user_factory, monkeypatch
):
    user_id = user_factory(email="delta-reset@example.com")
    service_id = service_factory(user_id=user_id, service_id=807)
    with app.app_context():
        _insert_item_link(service_id, "text:old", "pco-old")
        payloads = _payloads(
            [
                {"token": "text:1", "title": "Collect", "text": "Reset text."},
                {"token": "text:2", "title": "Gospel", "text": "Reset Gospel."},
            ]
        )
        deleted = []
        created = []
        monkeypatch.setattr(
            pco_sync,
            "list_plan_items",
            lambda *_args: [{"id": "pco-old"}, {"id": "manual-1"}],
        )
        monkeypatch.setattr(
            pco_sync, "delete_plan_item", lambda *args: deleted.append(args)
        )

        def fake_create(*args):
            created.append(args)
            return {"data": {"id": f"created-{len(created)}"}}

        monkeypatch.setattr(pco_sync, "create_plan_item", fake_create)

        pco_sync._reset_pco_plan_items(
            service_id, "base", "token", "type-1", "plan-1", payloads
        )

        assert [call[4] for call in deleted] == ["pco-old", "manual-1"]
        assert [call[4]["data"]["attributes"]["title"] for call in created] == [
            "Collect",
            "Gospel",
        ]
        links = (
            get_db()
            .execute(
                """
                select ordinarium_token, pco_item_id
                from service_pco_item_links
                where service_id=?
                order by last_position
                """,
                (service_id,),
            )
            .fetchall()
        )
        assert [(row["ordinarium_token"], row["pco_item_id"]) for row in links] == [
            ("text:1", "created-1"),
            ("text:2", "created-2"),
        ]
