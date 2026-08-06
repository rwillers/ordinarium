import json
import uuid

from ordinarium import pco_sync, text_routes
from ordinarium.db import get_database_gateway, get_db
from ordinarium.plan_items import build_plan_items
from ordinarium.service_store import load_service_for_text
from ordinarium.text_export import build_docx_render_context, build_text_export_context
from ordinarium.text_overrides import (
    canonical_text_for_house_use,
    upsert_user_text_override,
)
from ordinarium.text_rendering import build_rendered_ordinaries


HOUSE_ACCLAMATION = (
    "*&nbsp;* Blessed be God: Father, Son, and Holy Spirit.  \n"
    "*People* **And blessed be his kingdom, now and for ever. Amen.**"
)


def _canonical_text(text_type, **filters):
    clauses = ["type=?"]
    params = [text_type]
    for column, value in filters.items():
        clauses.append(f"{column}=?")
        params.append(value)
    return get_database_gateway().fetch_one(
        f"select id, type, title, detailed_title, default_order, text "
        f"from texts where {' and '.join(clauses)} order by id limit 1",
        params,
    )


def test_plan_item_preserves_identity_and_hides_options_for_house_use(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=401,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    with app.app_context():
        canonical = _canonical_text(
            "ordinarium",
            filter_type="rite",
            filter_content="Renewed Ancient Text",
            title="The Prayer of Consecration",
        )
        replacement = (
            "*Celebrant and People* **By him, and with him, and in him...**\n\n"
            "This remains an oblation."
        )
        upsert_user_text_override(user_id, canonical["id"], replacement)
        items = build_plan_items(service_id, "Renewed Ancient Text", [], [], user_id)
        item = next(row for row in items if row["id"] == canonical["id"])

    assert item["token"] == f"text:{canonical['id']}"
    assert item["canonical_type"] == "ordinarium"
    assert item["title"] == canonical["title"]
    assert item["default_order"] == canonical["default_order"]
    assert item["house_use_applied"] is True

    page = client.get(f"/service/{service_id}")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    row_start = body.index(f'data-plan-token="text:{canonical["id"]}"')
    row_end = body.index("</tr>", row_start)
    row_html = body[row_start:row_end]
    assert "House use applied" in row_html
    assert 'data-house-use-applied="true"' in row_html
    assert "data-service-option-key" not in row_html
    assert "data-service-option-edit" not in row_html

    generated_page = client.get(f"/service/{service_id}/view")
    assert generated_page.status_code == 200
    generated_html = generated_page.get_data(as_text=True)
    assert "House use applied" not in generated_html
    assert "text-element-house-use" not in generated_html


def test_house_use_applies_to_anonymous_share_and_is_account_scoped(
    app, client, service_factory, user_factory
):
    owner_id = user_factory(email="house-owner@example.com")
    other_id = user_factory(email="canonical-owner@example.com")
    owner_service_id = service_factory(
        user_id=owner_id,
        service_id=402,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    other_service_id = service_factory(
        user_id=other_id,
        service_id=403,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    owner_share = str(uuid.uuid4())
    other_share = str(uuid.uuid4())
    dangerous = HOUSE_ACCLAMATION + "\n\n<script>alert(1)</script> {{ 7 * 7 }}"
    with app.app_context():
        candidates = get_database_gateway().fetch_all(
            """
            select id from texts
            where type='acclamation'
              and ((filter_type='other' and filter_content='At Any Time')
                or (filter_type='day' and filter_content='The Lord’s Day'))
            """
        )
        for candidate in candidates:
            upsert_user_text_override(owner_id, candidate["id"], dangerous)
        saved_service, saved_data = load_service_for_text(owner_service_id)
        rendered = build_rendered_ordinaries(
            owner_service_id, saved_service, saved_data
        )
        acclamation_row = next(
            item for item in rendered if item["title"] == "The Acclamation"
        )
        plan_items = build_plan_items(
            owner_service_id,
            "Renewed Ancient Text",
            [],
            [],
            owner_id,
        )
        acclamation_plan_item = next(
            item for item in plan_items if item["title"] == "The Acclamation"
        )
        export = build_text_export_context(owner_service_id, saved_service, saved_data)
        acclamation_export = next(
            item for item in export["ordinaries"] if item["house_use_embedded"]
        )
        pco_payload = pco_sync.build_pco_item_payloads([acclamation_row])[0]
        db = get_db()
        db.executemany(
            "insert into service_shares (service_id, share_uuid) values (?, ?)",
            [(owner_service_id, owner_share), (other_service_id, other_share)],
        )
        db.commit()

    assert acclamation_row["house_use_applied"] is False
    assert acclamation_row["house_use_embedded"] is True
    assert acclamation_row["house_use_content"] is True
    assert acclamation_plan_item["house_use_supporting_configured"] is True
    assert "<script>alert(1)</script>" not in acclamation_export["body_html"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in acclamation_export["body_html"]
    pco_html = pco_payload["payload"]["data"]["attributes"]["html_details"]
    assert "<script>alert(1)</script>" not in pco_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in pco_html
    assert "{{ 7 * 7 }}" in pco_html
    assert "House use applied" not in pco_html

    owner_page = client.get(f"/share/{owner_share}").get_data(as_text=True)
    other_page = client.get(f"/share/{other_share}").get_data(as_text=True)
    assert "Blessed be God: Father, Son, and Holy Spirit" in owner_page
    assert "Blessed be God: Father, Son, and Holy Spirit" not in other_page
    assert "{{ 7 * 7 }}" in owner_page
    assert "49" not in owner_page
    assert "<script>alert(1)</script>" not in owner_page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in owner_page
    assert "House use applied" not in owner_page
    assert "text-element-house-use" not in owner_page


def test_templated_ordinary_override_renders_constrained_dynamic_slot_safely(
    app, user_factory, service_factory
):
    user_id = user_factory(email="templated-house@example.com")
    service_id = service_factory(
        user_id=user_id,
        service_id=410,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    with app.app_context():
        container = _canonical_text(
            "ordinarium",
            filter_type="rite",
            filter_content="Renewed Ancient Text",
            title="The Acclamation",
        )
        replacement = canonical_text_for_house_use(container["text"])
        replacement = (
            "*The Celebrant and People use the parish form.*\n\n"
            f"{replacement}\n\n{{{{ 7 * 7 }}}} <script>alert(1)</script>"
        )
        candidates = get_database_gateway().fetch_all(
            """
            select id from texts
            where type='acclamation'
              and ((filter_type='other' and filter_content='At Any Time')
                or (filter_type='day' and filter_content='The Lord’s Day'))
            """
        )
        for candidate in candidates:
            upsert_user_text_override(user_id, candidate["id"], HOUSE_ACCLAMATION)
        upsert_user_text_override(user_id, container["id"], replacement)

        saved_service, saved_data = load_service_for_text(service_id, user_id)
        rendered = build_rendered_ordinaries(
            service_id, saved_service, saved_data, user_id=user_id
        )
        row = next(
            item for item in rendered if item["token"] == f"text:{container['id']}"
        )
        export = build_text_export_context(
            service_id, saved_service, saved_data, user_id=user_id
        )
        export_row = next(
            item
            for item in export["ordinaries"]
            if item["title_markdown"] == "The Acclamation"
        )
        pco_payload = pco_sync.build_pco_item_payloads([row])[0]

    assert row["house_use_applied"] is True
    assert row["house_use_embedded"] is True
    assert "[[Acclamation text]]" not in row["text"]
    assert "Blessed be God: Father, Son, and Holy Spirit" in row["text"]
    assert "{{ 7 * 7 }}" in row["text"]
    assert "49" not in row["text"]
    assert "<script>alert(1)</script>" not in export_row["body_html"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in export_row["body_html"]
    pco_html = pco_payload["payload"]["data"]["attributes"]["html_details"]
    assert "Blessed be God: Father, Son, and Holy Spirit" in pco_html
    assert "{{ 7 * 7 }}" in pco_html
    assert "House use applied" not in pco_html


def test_ordinary_override_bypasses_options_and_is_safe_in_exports_and_pco(
    app, user_factory, service_factory
):
    user_id = user_factory(email="exports@example.com")
    service_id = service_factory(
        user_id=user_id,
        service_id=404,
        service_date="2026-01-04",
        rite="Anglican Standard Text",
        service_option_values={"consecration.oblation_term": "offering"},
    )
    replacement = (
        "*Celebrant and People* **By him, and with him, and in him...**\n\n"
        "Our local oblation.\n\n<img src=x onerror=alert(1)> {{ dangerous }}"
    )
    with app.app_context():
        canonical = _canonical_text(
            "ordinarium",
            filter_type="rite",
            filter_content="Anglican Standard Text",
            title="The Prayer of Consecration",
        )
        upsert_user_text_override(user_id, canonical["id"], replacement)
        saved_service, saved_data = load_service_for_text(service_id, user_id)
        rendered = build_rendered_ordinaries(
            service_id, saved_service, saved_data, user_id=user_id
        )
        row = next(
            item for item in rendered if item["token"] == f"text:{canonical['id']}"
        )
        export = build_text_export_context(
            service_id, saved_service, saved_data, user_id=user_id
        )
        export_row = next(
            item
            for item in export["ordinaries"]
            if item["house_use_applied"] and "By him" in item["body_html"]
        )
        docx_context = build_docx_render_context(export)
        pco_payload = pco_sync.build_pco_item_payloads([row])[0]

    assert row["house_use_applied"] is True
    assert "local oblation" in row["text"]
    assert "local offering" not in row["text"]
    assert "{{ dangerous }}" in row["text"]
    assert "<img src=x onerror=alert(1)>" not in export_row["body_html"]
    assert "&lt;img src=x onerror=alert(1)&gt;" in export_row["body_html"]
    assert any(item["house_use_applied"] for item in docx_context["ordinaries"])
    pco_html = pco_payload["payload"]["data"]["attributes"]["html_details"]
    assert "By him, and with him, and in him" in pco_html
    assert "<img src=x onerror=alert(1)>" not in pco_html
    assert "&lt;img src=x onerror=alert(1)&gt;" in pco_html
    assert "{{ dangerous }}" in pco_html
    assert "House use applied" not in pco_html


def test_cross_rite_selected_text_uses_override_and_preserves_provenance(
    app, user_factory, service_factory
):
    user_id = user_factory(email="cross-rite@example.com")
    service_id = service_factory(
        user_id=user_id,
        service_id=406,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        service_option_values={"post_communion.form": "other_rite"},
    )
    replacement = "*People* **Our parish post-communion prayer.** {{ literal }}"
    with app.app_context():
        source = _canonical_text(
            "ordinarium",
            filter_type="rite",
            filter_content="Anglican Standard Text",
            title="The Post Communion Prayer",
        )
        target = _canonical_text(
            "ordinarium",
            filter_type="rite",
            filter_content="Renewed Ancient Text",
            title="The Post Communion Prayer",
        )
        upsert_user_text_override(user_id, source["id"], replacement)
        saved_service, saved_data = load_service_for_text(service_id, user_id)
        rendered = build_rendered_ordinaries(
            service_id, saved_service, saved_data, user_id=user_id
        )

    row = next(item for item in rendered if item["token"] == f"text:{target['id']}")
    assert row["house_use_applied"] is True
    assert row["house_use_content"] is True
    assert "Our parish post-communion prayer" in row["text"]
    assert "{{ literal }}" in row["text"]


def test_render_pipeline_loads_override_map_once(
    app, monkeypatch, user_factory, service_factory
):
    user_id = user_factory(email="batched@example.com")
    service_id = service_factory(
        user_id=user_id,
        service_id=405,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    with app.app_context():
        saved_service, saved_data = load_service_for_text(service_id, user_id)
        from ordinarium import text_rendering

        original = text_rendering.load_user_text_overrides
        calls = []

        def recording_load(owner_user_id):
            calls.append(owner_user_id)
            return original(owner_user_id)

        monkeypatch.setattr(text_rendering, "load_user_text_overrides", recording_load)
        assert build_rendered_ordinaries(
            service_id, saved_service, saved_data, user_id=user_id
        )

    assert calls == [user_id]


def test_preview_request_reuses_one_override_map(
    app, auth_client, monkeypatch, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=407,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    with app.app_context():
        supporting = _canonical_text(
            "law_form",
            filter_type="rite",
            filter_content="Renewed Ancient Text",
        )
        upsert_user_text_override(
            user_id,
            supporting["id"],
            "House-use Decalogue text.",
        )
        canonical = _canonical_text(
            "ordinarium",
            filter_type="rite",
            filter_content="Renewed Ancient Text",
            title="The Summary of the Law",
        )

    from ordinarium import service_share_routes, text_rendering

    original = service_share_routes.load_user_text_overrides
    calls = []

    def recording_load(owner_user_id):
        calls.append(owner_user_id)
        return original(owner_user_id)

    monkeypatch.setattr(
        service_share_routes, "load_user_text_overrides", recording_load
    )

    def unexpected_load(_owner_user_id):
        raise AssertionError("render pipeline loaded a second override map")

    monkeypatch.setattr(text_rendering, "load_user_text_overrides", unexpected_load)
    response = client.post(
        f"/service/{service_id}/service-option-preview",
        json={
            "row_token": f"text:{canonical['id']}",
            "option_values": {"law.form": "decalogue"},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["house_use_applied"] is False
    assert payload["house_use_embedded"] is True
    assert payload["house_use_content"] is True
    assert "House-use Decalogue text" in payload["preview_html"]
    assert calls == [user_id]

    service_page = client.get(f"/service/{service_id}").get_data(as_text=True)
    assert "data.house_use_content" in service_page
    assert "text-element-house-use" in service_page
    assert "House use applied" in service_page


def test_copy_and_reorder_keep_canonical_token_without_duplicate_override(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=408,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    with app.app_context():
        canonical = _canonical_text(
            "ordinarium",
            filter_type="rite",
            filter_content="Renewed Ancient Text",
            title="The Prayer of Consecration",
        )
        token = f"text:{canonical['id']}"
        upsert_user_text_override(user_id, canonical["id"], "Local prayer")

    reorder = client.patch(
        f"/service/{service_id}",
        data={
            "ids": token,
            "disabled": "",
            "rite": "Renewed Ancient Text",
            "service_date": "2026-01-04",
            "autosave": "1",
        },
        headers={"Accept": "application/json"},
    )
    assert reorder.status_code == 200

    copied = client.post(
        "/services",
        data={
            "mode": "copy",
            "from_service_id": str(service_id),
            "rite": "Renewed Ancient Text",
            "service_date": "2027-01-03",
        },
    )
    assert copied.status_code == 302

    with app.app_context():
        db = get_db()
        source = db.execute(
            "select text_order from services where id=?", (service_id,)
        ).fetchone()
        copied_service = db.execute(
            """
            select id, text_order from services
            where user_id=? and id<>?
            order by id desc limit 1
            """,
            (user_id, service_id),
        ).fetchone()
        override_count = db.execute(
            """
            select count(*) from user_text_overrides
            where user_id=? and text_id=?
            """,
            (user_id, canonical["id"]),
        ).fetchone()[0]

    assert json.loads(source["text_order"]) == [token]
    assert json.loads(copied_service["text_order"]) == [token]
    assert override_count == 1


def test_pdf_and_docx_routes_export_house_use_safely(
    app, auth_client, monkeypatch, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=409,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
    )
    replacement = (
        "*Celebrant and People* **By him, and with him, and in him...**\n\n"
        "<script>alert('export')</script>"
    )
    with app.app_context():
        canonical = _canonical_text(
            "ordinarium",
            filter_type="rite",
            filter_content="Renewed Ancient Text",
            title="The Prayer of Consecration",
        )
        upsert_user_text_override(user_id, canonical["id"], replacement)

    captured = {}

    def fake_render(export_format, payload):
        captured[export_format] = payload
        return b"%PDF-house" if export_format == "pdf" else b"PK\x03\x04house"

    monkeypatch.setattr(text_routes, "render_document", fake_render)
    app.config["DOCUMENT_SERVICE_URL"] = "http://documents.internal/render"

    pdf_response = client.get(f"/service/{service_id}/export.pdf")
    docx_response = client.get(f"/service/{service_id}/export.docx")

    assert pdf_response.status_code == 200
    assert docx_response.status_code == 200
    pdf_html = captured["pdf"]["html"]
    assert "By him, and with him, and in him" in pdf_html
    assert "House use applied" not in pdf_html
    assert "text-element-house-use" not in pdf_html
    assert "<script>alert('export')</script>" not in pdf_html
    assert "&lt;script&gt;alert('export')&lt;/script&gt;" in pdf_html

    docx_rows = captured["docx"]["context"]["ordinaries"]
    house_row = next(row for row in docx_rows if row["house_use_applied"])
    assert "By him, and with him, and in him" in house_row["body_html"]
    assert "House use applied" not in str(captured["docx"]["context"])
    assert "<script>alert('export')</script>" not in house_row["body_html"]
    assert "&lt;script&gt;alert('export')&lt;/script&gt;" in house_row["body_html"]
