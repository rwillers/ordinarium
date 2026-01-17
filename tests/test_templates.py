import json

from ordinarium.db import get_db


def create_template(app, user_id, title="Template", text=""):
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            "insert into service_custom_templates (user_id, title, text) values (?, ?, ?)",
            (user_id, title, text),
        )
        db.commit()
        return cursor.lastrowid


def test_templates_requires_login_redirects_when_logged_out(client):
    response = client.get("/templates")
    assert response.status_code == 302
    location = response.headers.get("Location", "")
    assert "/login" in location
    assert "next=" in location and "templates" in location


def test_templates_create_and_list(app, auth_client):
    client, user_id = auth_client
    response = client.post(
        "/templates",
        data={"title": "Seasonal Template", "text": "Blessing text"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/templates")
    with app.app_context():
        db = get_db()
        template = db.execute(
            "select id, title, text from service_custom_templates where user_id=? limit 1",
            (user_id,),
        ).fetchone()
        assert template is not None
        assert template["title"] == "Seasonal Template"
        assert template["text"] == "Blessing text"
    response = client.get("/templates")
    assert response.status_code == 200
    assert b"Seasonal Template" in response.data
    assert b"Blessing text" in response.data


def test_templates_edit_updates_content(app, auth_client):
    client, user_id = auth_client
    template_id = create_template(app, user_id, title="Old", text="Original")
    response = client.post(
        "/templates",
        data={"template_id": str(template_id), "title": "New", "text": "Updated"},
    )
    assert response.status_code == 302
    with app.app_context():
        db = get_db()
        updated = db.execute(
            "select title, text from service_custom_templates where id=? limit 1",
            (template_id,),
        ).fetchone()
        assert updated["title"] == "New"
        assert updated["text"] == "Updated"


def test_templates_delete_removes_template(app, auth_client):
    client, user_id = auth_client
    template_id = create_template(app, user_id, title="Delete Me", text="Remove")
    response = client.post(f"/templates/{template_id}/delete")
    assert response.status_code == 302
    with app.app_context():
        db = get_db()
        deleted = db.execute(
            "select id from service_custom_templates where id=? limit 1",
            (template_id,),
        ).fetchone()
        assert deleted is None


def test_templates_edit_denies_other_user(app, auth_client, user_factory):
    client, _ = auth_client
    other_user_id = user_factory(email="other@example.com")
    template_id = create_template(app, other_user_id, title="Other", text="Nope")
    response = client.post(
        "/templates",
        data={"template_id": str(template_id), "title": "New", "text": "Update"},
    )
    assert response.status_code == 404


def test_templates_delete_denies_other_user(app, auth_client, user_factory):
    client, _ = auth_client
    other_user_id = user_factory(email="other2@example.com")
    template_id = create_template(app, other_user_id, title="Other", text="Nope")
    response = client.post(f"/templates/{template_id}/delete")
    assert response.status_code == 404


def test_templates_sorted_by_recent_update(app, auth_client):
    client, user_id = auth_client
    first_id = create_template(app, user_id, title="First Template", text="One")
    second_id = create_template(app, user_id, title="Second Template", text="Two")
    with app.app_context():
        db = get_db()
        db.execute(
            "update service_custom_templates set updated_at=? where id=?",
            ("2099-01-01 00:00:00", first_id),
        )
        db.execute(
            "update service_custom_templates set updated_at=? where id=?",
            ("2000-01-01 00:00:00", second_id),
        )
        db.commit()
    response = client.get("/templates")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert body.index("First Template") < body.index("Second Template")


def test_service_page_includes_template_select(app, auth_client, service_factory):
    client, user_id = auth_client
    template_id = create_template(app, user_id, title="Service Template", text="Text")
    service_id = service_factory(
        user_id=user_id,
        service_id=77,
        service_date="2026-01-04",
        rite="Renewed Ancient Text",
        text_order=json.dumps([68, 69]),
        text_disabled=json.dumps([]),
    )
    response = client.get(f"/service/{service_id}")
    assert response.status_code == 200
    assert b"Apply template" in response.data
    assert f'value="{template_id}"'.encode() in response.data
    assert b"Service Template" in response.data
