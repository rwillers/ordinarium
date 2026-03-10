import re

from ordinarium.db import get_db
from ordinarium.pco_sync import _load_service_plan
from ordinarium.text_rendering import _swap_communion_distribution_formulas


def _set_greeting_response_form(app, user_id, value):
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set greeting_response_form=? where id=?",
            (value, user_id),
        )
        db.commit()


def _plan_row_token_for_title(html, title):
    pattern = re.compile(
        rf'data-plan-token="([^"]+)"\s+data-ordinary-title="{re.escape(title)}"'
    )
    match = pattern.search(html or "")
    return match.group(1) if match else ""


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
    assert "data-plan-preset-select" in html
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


def test_init_db_ingests_creed_and_confession_option_texts(app):
    with app.app_context():
        db = get_db()
        rows = db.execute(
            """
            select filter_content, title, text
            from texts
            where type=?
              and filter_type=?
              and filter_content in (?, ?, ?)
            order by filter_content
            """,
            (
                "ordinarium",
                "handle",
                "confession.morning_prayer",
                "creed.apostles",
                "creed.athanasian",
            ),
        ).fetchall()

    assert [row["filter_content"] for row in rows] == [
        "confession.morning_prayer",
        "creed.apostles",
        "creed.athanasian",
    ]
    assert rows[0]["title"] == "The Confession and Absolution of Sin"
    assert "Dearly beloved, the Scriptures teach us to acknowledge" in rows[0]["text"]
    assert "and apart from your grace, there is no health in us." in rows[0]["text"]
    assert rows[1]["title"] == "The Apostles’ Creed"
    assert "I believe in God, the Father almighty," in rows[1]["text"]
    assert rows[2]["title"] == "The Athanasian Creed"
    assert "Whosoever will be saved, *" in rows[2]["text"]


def test_service_option_preview_uses_apostles_and_athanasian_creeds(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_factory(
        user_id=user_id,
        service_id=606,
        title="Trinity Sunday",
        service_date="2026-05-31",
        observance_handle="TrinitySunday",
    )

    service_response = client.get("/service/606")
    assert service_response.status_code == 200
    row_token = _plan_row_token_for_title(
        service_response.get_data(as_text=True),
        "The Nicene Creed",
    )
    assert row_token == "text:80"

    apostles_response = client.post(
        "/service/606/service-option-preview",
        json={"row_token": row_token, "option_values": {"creed.form": "apostles"}},
        headers={"Accept": "application/json"},
    )
    assert apostles_response.status_code == 200
    apostles_payload = apostles_response.get_json()
    assert apostles_payload["ok"] is True
    assert apostles_payload["title"] == "The Apostles’ Creed"
    assert "I believe in God, the Father almighty," in apostles_payload["preview_html"]
    assert "We believe in one God," not in apostles_payload["preview_html"]

    athanasian_response = client.post(
        "/service/606/service-option-preview",
        json={"row_token": row_token, "option_values": {"creed.form": "athanasian"}},
        headers={"Accept": "application/json"},
    )
    assert athanasian_response.status_code == 200
    athanasian_payload = athanasian_response.get_json()
    assert athanasian_payload["ok"] is True
    assert athanasian_payload["title"] == "The Athanasian Creed"
    assert "Whosoever will be saved," in athanasian_payload["preview_html"]
    assert "We believe in one God," not in athanasian_payload["preview_html"]


def test_view_can_use_other_rite_and_morning_prayer_confession_forms(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_factory(
        user_id=user_id,
        service_id=607,
        title="Ordinary Time",
        service_date="2026-01-18",
        observance_handle="EpiphanyII",
        service_option_values={"confession.form": "other_rite"},
    )
    service_factory(
        user_id=user_id,
        service_id=608,
        title="Ordinary Time",
        service_date="2026-01-18",
        observance_handle="EpiphanyII",
        service_option_values={"confession.form": "morning_prayer"},
    )

    other_rite_response = client.get("/service/607/view")
    assert other_rite_response.status_code == 200
    other_rite_html = other_rite_response.get_data(as_text=True)
    assert "Almighty God, Father of our Lord Jesus Christ," in other_rite_html
    assert "Most merciful God," not in other_rite_html

    morning_prayer_response = client.get("/service/608/view")
    assert morning_prayer_response.status_code == 200
    morning_prayer_html = morning_prayer_response.get_data(as_text=True)
    assert (
        "Dearly beloved, the Scriptures teach us to acknowledge our many sins and offenses"
        in morning_prayer_html
    )
    assert "and apart from your grace, there is no health in us." in morning_prayer_html
    assert (
        "Grant to your faithful people, merciful Lord, pardon and peace"
        in morning_prayer_html
    )


def test_service_options_accept_new_creed_confession_and_distribution_keys(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_factory(
        user_id=user_id,
        service_id=609,
        title="Trinity Sunday",
        service_date="2026-05-31",
        observance_handle="TrinitySunday",
    )

    response = client.post(
        "/service/609/service-options",
        json={
            "option_values": {
                "creed.form": "apostles",
                "confession.form": "morning_prayer",
                "communion.distribution.source_rite": "other_rite",
            }
        },
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["service_option_values"]["creed.form"] == "apostles"
    assert payload["service_option_values"]["confession.form"] == "morning_prayer"
    assert (
        payload["service_option_values"]["communion.distribution.source_rite"]
        == "other_rite"
    )


def test_swap_communion_distribution_formulas_replaces_only_distribution_words():
    current_text = (
        "*Facing the People, the Celebrant may say the following invitation*\n\n"
        "Invitation paragraph.\n\n"
        "*The Bread and Cup are given to the communicants with these words*\n\n"
        "The Body of our Lord Jesus Christ, [current body formula]\n\n"
        "The Blood of our Lord Jesus Christ, [current blood formula]\n\n"
        "*During the ministration of Communion, hymns may be sung.*"
    )
    other_rite_text = (
        "*Facing the People, the Celebrant may say the following invitation*\n\n"
        "Different invitation paragraph.\n\n"
        "*The Bread and Cup are given to the communicants with these words*\n\n"
        "The Body of our Lord Jesus Christ, [other body formula]\n\n"
        "The Blood of our Lord Jesus Christ, [other blood formula]\n\n"
        "*During the ministration of Communion, a psalm may be sung.*"
    )

    swapped = _swap_communion_distribution_formulas(current_text, other_rite_text)

    assert "Invitation paragraph." in swapped
    assert "Different invitation paragraph." not in swapped
    assert "[other body formula]" in swapped
    assert "[other blood formula]" in swapped
    assert "hymns may be sung" in swapped
    assert "a psalm may be sung" not in swapped
