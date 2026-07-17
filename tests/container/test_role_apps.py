import container_role_apps
from container_role_apps import create_documents_app, create_jobs_app


def test_documents_health_endpoint():
    response = create_documents_app().test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"role": "documents", "status": "ok"}


def test_jobs_health_endpoint(monkeypatch):
    monkeypatch.setenv("ORDINARIUM_CONTAINER_ROLE", "email-jobs")

    response = create_jobs_app().test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"role": "email-jobs", "status": "ok"}


def test_private_container_apps_do_not_expose_business_routes():
    for app in (create_documents_app(), create_jobs_app()):
        response = app.test_client().get("/")

        assert response.status_code == 404


def test_documents_render_endpoint_returns_pdf(monkeypatch):
    monkeypatch.setattr(
        container_role_apps, "render_pdf_bytes", lambda html, base_url=None: b"%PDF-ok"
    )

    response = (
        create_documents_app()
        .test_client()
        .post("/render", json={"format": "pdf", "html": "<p>ok</p>"})
    )

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data == b"%PDF-ok"
    assert float(response.headers["X-Ordinarium-Render-Ms"]) >= 0
    assert int(response.headers["X-Ordinarium-Peak-Rss-Kib"]) > 0


def test_documents_render_endpoint_rejects_unknown_format():
    response = (
        create_documents_app().test_client().post("/render", json={"format": "unknown"})
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_payload"
