import json
import uuid

import pytest

from ordinarium.db import get_db
from ordinarium.pco_sync import _load_service_plan
from ordinarium.plan_items import build_plan_items
from ordinarium.service_store import load_service_for_text
from ordinarium.text_export import build_text_export_context


@pytest.mark.parametrize("rite", ["Renewed Ancient Text", "Anglican Standard Text"])
@pytest.mark.parametrize("mode", ["kyrie", "trisagion"])
@pytest.mark.parametrize("before_songs", [True, False])
def test_saved_penitential_row_order_is_used_by_renderers(
    app, auth_client, service_factory, rite, mode, before_songs
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=45,
        service_date="2026-01-04",
        rite=rite,
        service_option_values={"penitential_song.mode": mode},
    )
    share_uuid = str(uuid.uuid4())
    with app.app_context():
        db = get_db()
        for custom_id, title in [(1, "First worship song"), (2, "Second worship song")]:
            db.execute(
                "insert into service_custom_elements (id, service_id, user_id, title, text) values (?, ?, ?, ?, ?)",
                (custom_id, service_id, user_id, title, "Song lyrics"),
            )
        db.execute(
            "insert into service_shares (service_id, share_uuid) values (?, ?)",
            (service_id, share_uuid),
        )
        db.commit()
        items = build_plan_items(service_id, rite, [], [], user_id=user_id)
        kyrie = next(item for item in items if item["title"] == "The Kyrie")
        trisagion = next(item for item in items if item["title"] == "The Trisagion")

    # Dragging the visible Kyrie / Trisagion row does not move its hidden alternate.
    order = (
        [kyrie["token"], "custom:1", "custom:2", trisagion["token"]]
        if before_songs
        else [trisagion["token"], "custom:1", "custom:2", kyrie["token"]]
    )
    order.extend(item["token"] for item in items if item["token"] not in order)
    response = client.patch(
        f"/service/{service_id}",
        data={"ids": ",".join(order), "autosave": "1"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    editor = client.get(f"/service/{service_id}").get_data(as_text=True)
    assert (
        editor.index(f'data-plan-token="{kyrie["token"]}"')
        < editor.index('data-plan-token="custom:1"')
    ) == before_songs
    selected_title = "The Trisagion" if mode == "trisagion" else "The Kyrie"
    selected_token = trisagion["token"] if mode == "trisagion" else kyrie["token"]
    expected_titles = (
        [selected_title, "First worship song", "Second worship song"]
        if before_songs
        else ["First worship song", "Second worship song", selected_title]
    )
    for path in [f"/service/{service_id}/view", f"/share/{share_uuid}"]:
        response = client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        positions = [html.index(title) for title in expected_titles]
        assert positions == sorted(positions)
        assert html.count(selected_title) == 1

    with app.app_context():
        saved, data = load_service_for_text(service_id, user_id)
        assert json.loads(saved["text_order"]) == order
        exported = build_text_export_context(service_id, saved, data, user_id)
        assert [
            row["title_markdown"] for row in exported["ordinaries"][:3]
        ] == expected_titles
        _, pco_items = _load_service_plan(service_id, user_id)
        assert [row["title"] for row in pco_items[:3]] == expected_titles
        assert (
            next(row for row in pco_items if row["title"] == selected_title)["token"]
            == selected_token
        )

    preview = client.post(
        f"/service/{service_id}/service-option-preview",
        json={"row_token": kyrie["token"], "option_values": {}},
    )
    assert preview.status_code == 200
    assert preview.get_json()["title"] == selected_title


@pytest.mark.parametrize("mode", ["kyrie", "trisagion"])
def test_disabled_visible_penitential_row_omits_both_alternatives(
    app, auth_client, service_factory, mode
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=45,
        service_date="2026-01-04",
        service_option_values={"penitential_song.mode": mode},
    )
    with app.app_context():
        items = build_plan_items(service_id, "Renewed Ancient Text", [], [])
        kyrie = next(item for item in items if item["title"] == "The Kyrie")
        db = get_db()
        db.execute(
            "update services set text_disabled=? where id=?",
            (json.dumps([kyrie["token"]]), service_id),
        )
        db.commit()

    response = client.get(f"/service/{service_id}/view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "The Kyrie" not in html
    assert "The Trisagion" not in html
