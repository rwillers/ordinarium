from ordinarium import text_routes


def test_pdf_export_dispatches_to_document_service(
    app, auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    service_id = service_factory(user_id=user_id, service_id=301)
    captured = {}

    def fake_render(export_format, payload):
        captured.update(format=export_format, payload=payload)
        return b"%PDF-remote"

    monkeypatch.setattr(text_routes, "render_document", fake_render)
    app.config["DOCUMENT_SERVICE_URL"] = "http://documents.internal/render"

    response = client.get(f"/service/{service_id}/export.pdf")

    assert response.status_code == 200
    assert response.data == b"%PDF-remote"
    assert captured["format"] == "pdf"
    assert "<html" in captured["payload"]["html"]


def test_docx_export_dispatches_context_to_document_service(
    app, auth_client, service_factory, monkeypatch
):
    client, user_id = auth_client
    service_id = service_factory(user_id=user_id, service_id=302)
    captured = {}

    def fake_render(export_format, payload):
        captured.update(format=export_format, payload=payload)
        return b"PK\x03\x04remote"

    monkeypatch.setattr(text_routes, "render_document", fake_render)
    app.config["DOCUMENT_SERVICE_URL"] = "http://documents.internal/render"

    response = client.get(f"/service/{service_id}/export.docx")

    assert response.status_code == 200
    assert response.data.startswith(b"PK\x03\x04")
    assert captured["format"] == "docx"
    document_context = captured["payload"]["context"]
    assert "service_id" not in document_context
    assert set(document_context) == {
        "generated_at_display",
        "ordinaries",
        "rite",
        "service_date_display",
        "service_title",
        "title",
    }
