from ordinarium.db import get_db
from ordinarium.pco_sync import _load_service_plan


def _set_greeting_response_form(app, user_id, value):
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set greeting_response_form=? where id=?",
            (value, user_id),
        )
        db.commit()


def test_service_page_shows_trinity_rubric_hints_and_presets(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_factory(
        user_id=user_id,
        service_id=601,
        title="Trinity Sunday",
        service_date="2026-05-31",
        observance_handle="TrinitySunday",
    )

    response = client.get("/service/601")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Rubric hints" in html
    assert "The Exhortation is traditionally read on Trinity Sunday." in html
    assert "The Athanasian Creed may be used on Trinity Sunday." in html
    assert "Reorder:" in html
    assert 'data-plan-preset-select' in html
    assert '<option value="default">Default order</option>' in html
    assert '<option value="penitential">Penitential Order</option>' in html


def test_service_page_omits_rubric_hints_when_no_observance_match(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_factory(
        user_id=user_id,
        service_id=602,
        title="First Sunday after Epiphany",
        service_date="2026-01-11",
        observance_handle="EpiphanyI",
    )

    response = client.get("/service/602")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Rubric hints" not in html


def test_view_share_preview_and_pco_use_greeting_response_preference(
    app, auth_client, service_factory
):
    client, user_id = auth_client
    service_factory(
        user_id=user_id,
        service_id=603,
        title="First Sunday after Christmas",
        service_date="2026-01-04",
        observance_handle="ChristmasI",
    )
    _set_greeting_response_form(app, user_id, "also_with_you")

    view_response = client.get("/service/603/view")
    assert view_response.status_code == 200
    view_html = view_response.data.decode("utf-8")
    assert "And also with you." in view_html
    assert "And with your spirit." not in view_html

    share_payload = client.post("/service/603/share").get_json()
    share_response = client.get(f"/share/{share_payload['share_uuid']}")
    assert share_response.status_code == 200
    share_html = share_response.data.decode("utf-8")
    assert "And also with you." in share_html
    assert "And with your spirit." not in share_html

    preview_response = client.post(
        "/service/603/service-option-preview",
        json={"row_token": "text:86", "option_values": {}},
        headers={"Accept": "application/json"},
    )
    assert preview_response.status_code == 200
    preview_payload = preview_response.get_json()
    assert preview_payload["ok"] is True
    assert "And also with you." in preview_payload["preview_html"]

    with app.app_context():
        _saved_service, ordinaries = _load_service_plan(603, user_id)
    assert any("And also with you." in (item.get("text") or "") for item in ordinaries)


def test_rat_service_can_use_ast_prayers_straight_through_via_service_options(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_factory(
        user_id=user_id,
        service_id=604,
        title="Ordinary Time",
        service_date="2026-01-18",
        observance_handle="EpiphanyII",
    )

    response = client.post(
        "/service/604/service-options",
        json={
            "option_values": {
                "prayers.form": "ast",
                "prayers.ast.delivery": "straight_through",
            }
        },
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["service_option_values"]["prayers.form"] == "ast"
    assert (
        payload["service_option_values"]["prayers.ast.delivery"] == "straight_through"
    )

    view_response = client.get("/service/604/view")
    assert view_response.status_code == 200
    view_html = view_response.data.decode("utf-8")
    assert "Let us pray for the Church and for the world." in view_html
    assert "Lord, in your mercy:" not in view_html
    assert "Hear our prayer." not in view_html


def test_ast_view_uses_consecration_and_humble_access_overrides(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_factory(
        user_id=user_id,
        service_id=605,
        title="Trinity Sunday",
        rite="Anglican Standard Text",
        service_date="2026-05-31",
        observance_handle="TrinitySunday",
        service_option_values={
            "consecration.oblation_term": "offering",
            "consecration.memorial_form": "alternate_acclamation",
            "humble_access.grace_intro": "insert_apart_from_your_grace",
        },
    )

    response = client.get("/service/605/view")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "one offering of himself once offered" in html
    assert "offering, and satisfaction" in html
    assert "Therefore we proclaim the mystery of faith:" in html
    assert "Therefore, O Lord and heavenly Father" not in html
    assert "Apart from your grace, we are not worthy so much as to gather up" in html
