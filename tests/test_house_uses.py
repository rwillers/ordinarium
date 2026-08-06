from flask.testing import FlaskClient

from ordinarium.db import get_database_gateway
from ordinarium.text_overrides import (
    canonical_text_for_house_use,
    canonical_text_hash,
    load_user_text_overrides,
    upsert_user_text_override,
)


def test_house_uses_requires_login(client):
    response = client.get("/house-uses")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert "house-uses" in response.headers["Location"]


def test_house_uses_lists_texts_by_rite_and_source_with_navigation(auth_client):
    client, _user_id = auth_client

    response = client.get("/house-uses?group=all")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "<h2>Settings</h2>" in body
    assert "<h3>House-use texts</h3>" in body
    assert "Renewed Ancient Text" in body
    assert "Anglican Standard Text" in body
    assert "Renewed Ancient Text — Opening" in body
    assert "Renewed Ancient Text — Word and prayers" in body
    assert "Renewed Ancient Text — Holy Communion" in body
    assert "Renewed Ancient Text — Conclusion" in body
    assert "Seasonal and occasional acclamations" in body
    assert "Offertory sentences" in body
    assert "Proper prefaces" in body
    assert "Official text" in body
    assert "Local replacement (Markdown)" in body
    assert 'name="group"' in body
    assert "Currently customized (0)" in body
    assert "All house-use texts" in body
    assert 'href="/settings/house-uses" aria-current="page"' in body
    assert "<details" in body
    assert "<details open" not in body


def test_house_uses_canonical_route_requires_login(client):
    response = client.get("/settings/house-uses")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert "settings%2Fhouse-uses" in response.headers["Location"]


def test_house_uses_defaults_to_preferred_rite_and_filters_on_the_server(auth_client):
    client, _user_id = auth_client

    preferred = client.get("/house-uses").get_data(as_text=True)
    acclamations = client.get("/house-uses?group=acclamations").get_data(as_text=True)

    assert '<option value="rite-renewed-ancient-text" selected>' in preferred
    assert "Renewed Ancient Text — Opening" in preferred
    assert "Anglican Standard Text — Opening" not in preferred
    assert "Seasonal and occasional acclamations" not in preferred
    assert '<option value="acclamations" selected>' in acclamations
    assert "Seasonal and occasional acclamations" in acclamations
    assert "Renewed Ancient Text — Opening" not in acclamations


def test_house_uses_defaults_to_currently_customized_when_overrides_exist(
    app, auth_client
):
    client, user_id = auth_client
    with app.app_context():
        canonical = _plain_text("acclamation")
        upsert_user_text_override(user_id, canonical["id"], "Local acclamation")

    body = client.get("/house-uses").get_data(as_text=True)

    assert '<option value="customized" selected>' in body
    assert f'id="text-{canonical["id"]}"' in body
    assert "Currently customized (1)" in body
    assert body.count('class="house-use-card has-override"') == 1


def test_house_use_save_preserves_markdown_whitespace(app, auth_client):
    client, user_id = auth_client
    replacement = "  *Celebrant and People*  \n\n    By him, and with him\n"
    with app.app_context():
        canonical = _plain_text("ordinarium")

    response = client.post(
        f"/house-uses/{canonical['id']}/save",
        data={"replacement_text": replacement},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"House use saved." in response.data
    assert b"House use applied" in response.data
    with app.app_context():
        override = load_user_text_overrides(user_id)[canonical["id"]]
        assert override["replacement_text"] == replacement


def test_restore_deletes_only_current_users_override(app, auth_client, user_factory):
    client, user_id = auth_client
    second_user_id = user_factory(email="other-house@example.com")
    with app.app_context():
        canonical = _plain_text("acclamation")
        upsert_user_text_override(user_id, canonical["id"], "First parish")
        upsert_user_text_override(second_user_id, canonical["id"], "Second parish")

    response = client.post(
        f"/house-uses/{canonical['id']}/restore", follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Official text restored." in response.data
    with app.app_context():
        assert canonical["id"] not in load_user_text_overrides(user_id)
        assert (
            load_user_text_overrides(second_user_id)[canonical["id"]][
                "replacement_text"
            ]
            == "Second parish"
        )


def test_stale_override_can_be_acknowledged_without_changing_replacement(
    app, auth_client
):
    client, user_id = auth_client
    replacement = "Local parish form"
    with app.app_context():
        canonical = _plain_text("ordinarium")
        upsert_user_text_override(user_id, canonical["id"], replacement)
        revised_text = canonical["text"] + "\n\nOfficial revision"
        get_database_gateway().execute(
            "update texts set text=? where id=?",
            (revised_text, canonical["id"]),
        )
        current_text_hash = canonical_text_hash(revised_text)

    page = client.get("/house-uses")
    assert b"Official text changed&mdash;review local version." in page.data
    assert b"Review updated official text" in page.data

    response = client.post(
        f"/house-uses/{canonical['id']}/review",
        data={"current_text_hash": current_text_hash},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Official text review acknowledged." in response.data
    assert b"Official text changed&mdash;review local version." not in response.data
    with app.app_context():
        override = load_user_text_overrides(user_id)[canonical["id"]]
        assert override["replacement_text"] == replacement
        assert override["is_stale"] is False
        assert override["base_text_hash"] == current_text_hash


def test_plain_override_remains_visible_and_reviewable_after_becoming_templated(
    app, auth_client
):
    client, user_id = auth_client
    replacement = "Active local wording"
    with app.app_context():
        canonical = _plain_text("ordinarium")
        upsert_user_text_override(user_id, canonical["id"], replacement)
        templated_text = canonical["text"] + "\n\n{{ newly_templated }}"
        get_database_gateway().execute(
            "update texts set text=? where id=?", (templated_text, canonical["id"])
        )
        current_text_hash = canonical_text_hash(templated_text)

    page = client.get("/house-uses")

    assert page.status_code == 200
    body = page.data.decode("utf-8")
    card = body.split(f'id="text-{canonical["id"]}"', 1)[1].split("</details>", 1)[0]
    assert "Editing locked" in card
    assert "Active local wording" in card
    assert "readonly" in card
    assert f'/settings/house-uses/{canonical["id"]}/restore' in card
    assert f'/settings/house-uses/{canonical["id"]}/review' in card
    assert f'/settings/house-uses/{canonical["id"]}/save' not in card
    assert f'name="current_text_hash" value="{current_text_hash}"' in card

    rejected_save = client.post(
        f"/house-uses/{canonical['id']}/save",
        data={"replacement_text": "Attempted edit"},
    )
    acknowledged = client.post(
        f"/house-uses/{canonical['id']}/review",
        data={"current_text_hash": current_text_hash},
        follow_redirects=True,
    )

    assert rejected_save.status_code == 400
    assert acknowledged.status_code == 200
    assert b"Official text review acknowledged." in acknowledged.data
    with app.app_context():
        override = load_user_text_overrides(user_id)[canonical["id"]]
        assert override["replacement_text"] == replacement
        assert override["is_stale"] is False


def test_review_rejects_an_unseen_canonical_revision(app, auth_client):
    client, user_id = auth_client
    with app.app_context():
        canonical = _plain_text("ordinarium")
        upsert_user_text_override(user_id, canonical["id"], "Local wording")
        first_revision = canonical["text"] + "\n\nFirst revision"
        get_database_gateway().execute(
            "update texts set text=? where id=?", (first_revision, canonical["id"])
        )
        displayed_hash = canonical_text_hash(first_revision)
        second_revision = first_revision + "\n\nSecond unseen revision"
        get_database_gateway().execute(
            "update texts set text=? where id=?", (second_revision, canonical["id"])
        )

    response = client.post(
        f"/house-uses/{canonical['id']}/review",
        data={"current_text_hash": displayed_hash},
    )

    assert response.status_code == 409
    assert b"Official text changed again" in response.data
    with app.app_context():
        override = load_user_text_overrides(user_id)[canonical["id"]]
        assert override["base_text_hash"] == canonical_text_hash(canonical["text"])
        assert override["current_text_hash"] == canonical_text_hash(second_revision)
        assert override["is_stale"] is True


def test_save_accepts_supported_template_slots(app, auth_client):
    client, user_id = auth_client
    with app.app_context():
        templated = get_database_gateway().fetch_one(
            """
            select id, text from texts
            where type='ordinarium' and text like '%{{%'
            order by id limit 1
            """
        )
        replacement = canonical_text_for_house_use(templated["text"])

    response = client.post(
        f"/house-uses/{templated['id']}/save",
        data={"replacement_text": replacement, "return_group": "all"},
    )

    assert response.status_code == 302
    assert "group=all" in response.headers["Location"]
    with app.app_context():
        assert (
            load_user_text_overrides(user_id)[templated["id"]]["replacement_text"]
            == replacement
        )


def test_template_slots_are_presented_as_friendly_editable_tokens(auth_client):
    client, _user_id = auth_client

    body = client.get("/house-uses?group=rite-renewed-ancient-text").get_data(
        as_text=True
    )

    assert "Dynamic text" in body
    assert "[[Acclamation text]]" in body
    assert "{{ acclamation | markdown }}" not in body


def test_save_rejects_unsupported_template_disallowed_missing_and_unknown_texts(
    app, auth_client
):
    client, _user_id = auth_client
    with app.app_context():
        gateway = get_database_gateway()
        templated = gateway.fetch_one(
            "select id from texts where type='ordinarium' and text like '%{{%' limit 1"
        )
        gateway.execute(
            "update texts set text=? where id=?",
            ("{% if dangerous %}Local{% endif %}", templated["id"]),
        )
        disallowed = gateway.fetch_one(
            "select id from texts where type='lesson' limit 1"
        )

    templated_response = client.post(
        f"/house-uses/{templated['id']}/save", data={"replacement_text": "Local"}
    )
    disallowed_response = client.post(
        f"/house-uses/{disallowed['id']}/save", data={"replacement_text": "Local"}
    )
    missing_response = client.post(
        f"/house-uses/{_plain_text_id(app, 'acclamation')}/save", data={}
    )
    unknown_response = client.post(
        "/house-uses/999999/save", data={"replacement_text": "Local"}
    )

    assert templated_response.status_code == 400
    assert b"unsupported dynamic logic" in templated_response.data
    assert disallowed_response.status_code == 400
    assert b"cannot be customized" in disallowed_response.data
    assert missing_response.status_code == 400
    assert unknown_response.status_code == 404


def test_restore_and_review_do_not_expose_another_accounts_override(
    app, auth_client, user_factory
):
    client, _user_id = auth_client
    second_user_id = user_factory(email="private-house@example.com")
    with app.app_context():
        canonical = _plain_text("acclamation")
        upsert_user_text_override(second_user_id, canonical["id"], "Private wording")

    restore = client.post(f"/house-uses/{canonical['id']}/restore")
    review = client.post(f"/house-uses/{canonical['id']}/review")

    assert restore.status_code == 404
    assert review.status_code == 404
    with app.app_context():
        assert (
            load_user_text_overrides(second_user_id)[canonical["id"]][
                "replacement_text"
            ]
            == "Private wording"
        )


def test_house_use_post_requires_csrf(app, user_factory):
    user_id = user_factory(email="csrf-house@example.com")
    with app.app_context():
        canonical = _plain_text("acclamation")
    app.config.update(WTF_CSRF_ENABLED=True)
    app.test_client_class = FlaskClient
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post(
        f"/house-uses/{canonical['id']}/save",
        data={"replacement_text": "Local"},
    )

    assert response.status_code == 400
    with app.app_context():
        assert canonical["id"] not in load_user_text_overrides(user_id)


def test_house_use_page_escapes_literal_jinja_and_raw_html(app, auth_client):
    client, user_id = auth_client
    replacement = "{{ config }}\n\n<script>alert('house-use')</script>"
    with app.app_context():
        canonical = _plain_text("acclamation")
        upsert_user_text_override(user_id, canonical["id"], replacement)

    response = client.get("/house-uses")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "{{ config }}" in body
    assert "<script>alert('house-use')</script>" not in body
    assert "&lt;script&gt;alert(&#39;house-use&#39;)&lt;/script&gt;" in body


def _plain_text(text_type):
    return get_database_gateway().fetch_one(
        """
        select id, type, filter_type, filter_content, text, title,
               detailed_title, default_order
        from texts
        where type=? and coalesce(text, '') not like '%{{%'
        order by id
        limit 1
        """,
        (text_type,),
    )


def _plain_text_id(app, text_type):
    with app.app_context():
        return _plain_text(text_type)["id"]
