import threading
import time

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


def test_job_process_endpoint_is_role_gated_and_authenticated(monkeypatch):
    monkeypatch.setenv("ORDINARIUM_CONTAINER_ROLE", "pco-jobs")
    monkeypatch.setenv("JOB_SERVICE_AUTH_TOKEN", "pco-secret")
    client = create_jobs_app().test_client()
    payload = {"job_id": "job-1", "row_id": "row-1", "user_id": 7}

    missing_auth = client.post("/jobs/pco/rows/process", json=payload)
    wrong_role = client.post(
        "/jobs/email/resets/process",
        json={"reset_id": "reset-1"},
        headers={"X-Ordinarium-Job-Auth": "pco-secret"},
    )
    unavailable = client.post(
        "/jobs/pco/rows/process",
        json=payload,
        headers={"X-Ordinarium-Job-Auth": "pco-secret"},
    )

    assert missing_auth.status_code == 404
    assert wrong_role.status_code == 404
    assert unavailable.status_code == 503
    assert unavailable.headers["Retry-After"] == "30"
    assert unavailable.get_json() == {
        "error": "processor_unavailable",
        "retry_after_seconds": 30,
    }


def test_job_endpoint_rejects_unbounded_payload_contract(monkeypatch):
    monkeypatch.setenv("ORDINARIUM_CONTAINER_ROLE", "email-jobs")
    monkeypatch.setenv("JOB_SERVICE_AUTH_TOKEN", "email-secret")
    client = create_jobs_app().test_client()
    headers = {"X-Ordinarium-Job-Auth": "email-secret"}

    extra_field = client.post(
        "/jobs/email/resets/process",
        json={"reset_id": "reset-1", "reset_token": "must-not-cross-boundary"},
        headers=headers,
    )
    wrong_type = client.post(
        "/jobs/email/resets/dead-letter",
        json={"reset_id": 1},
        headers=headers,
    )

    assert extra_field.status_code == 400
    assert wrong_type.status_code == 400


def test_private_container_apps_do_not_expose_business_routes():
    for app in (create_documents_app(), create_jobs_app()):
        response = app.test_client().get("/")

        assert response.status_code == 404


def test_documents_render_endpoint_returns_pdf(monkeypatch):
    monkeypatch.setenv("DOCUMENT_SERVICE_AUTH_TOKEN", "document-secret")
    monkeypatch.setattr(
        container_role_apps, "render_pdf_bytes", lambda html, base_url=None: b"%PDF-ok"
    )

    response = (
        create_documents_app()
        .test_client()
        .post(
            "/render",
            json={"format": "pdf", "html": "<p>ok</p>"},
            headers={"X-Ordinarium-Document-Auth": "document-secret"},
        )
    )

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data == b"%PDF-ok"
    assert float(response.headers["X-Ordinarium-Render-Ms"]) >= 0
    assert int(response.headers["X-Ordinarium-Peak-Rss-Kib"]) > 0


def test_documents_render_endpoint_rejects_unknown_format(monkeypatch):
    monkeypatch.setenv("DOCUMENT_SERVICE_AUTH_TOKEN", "document-secret")
    response = (
        create_documents_app()
        .test_client()
        .post(
            "/render",
            json={"format": "unknown"},
            headers={"X-Ordinarium-Document-Auth": "document-secret"},
        )
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_payload"


def test_documents_render_endpoint_requires_deployment_authentication(monkeypatch):
    monkeypatch.setenv("DOCUMENT_SERVICE_AUTH_TOKEN", "document-secret")
    client = create_documents_app().test_client()

    missing = client.post("/render", json={"format": "pdf", "html": "<p>ok</p>"})
    wrong = client.post(
        "/render",
        json={"format": "pdf", "html": "<p>ok</p>"},
        headers={"X-Ordinarium-Document-Auth": "wrong"},
    )

    assert missing.status_code == 404
    assert wrong.status_code == 404


def test_documents_render_endpoint_enforces_output_limit(monkeypatch):
    monkeypatch.setenv("DOCUMENT_SERVICE_AUTH_TOKEN", "document-secret")
    monkeypatch.setenv("DOCUMENT_MAX_OUTPUT_BYTES", "4")
    monkeypatch.setattr(
        container_role_apps, "render_pdf_bytes", lambda html, base_url=None: b"12345"
    )

    response = (
        create_documents_app()
        .test_client()
        .post(
            "/render",
            json={"format": "pdf", "html": "<p>ok</p>"},
            headers={"X-Ordinarium-Document-Auth": "document-secret"},
        )
    )

    assert response.status_code == 503
    assert response.get_json()["error"] == "render_failed"


def test_documents_render_endpoint_enforces_deadline_and_capacity(monkeypatch):
    monkeypatch.setenv("DOCUMENT_SERVICE_AUTH_TOKEN", "document-secret")
    monkeypatch.setenv("DOCUMENT_RENDER_TIMEOUT_SECONDS", "0.01")
    release_render = threading.Event()

    def slow_render(_format, _payload):
        release_render.wait(timeout=1)
        return b"%PDF-ok", "application/pdf"

    monkeypatch.setattr(container_role_apps, "_render_payload", slow_render)
    client = create_documents_app().test_client()
    headers = {"X-Ordinarium-Document-Auth": "document-secret"}

    timed_out = client.post(
        "/render", json={"format": "pdf", "html": "<p>ok</p>"}, headers=headers
    )
    at_capacity = client.post(
        "/render", json={"format": "pdf", "html": "<p>ok</p>"}, headers=headers
    )
    release_render.set()

    assert timed_out.status_code == 503
    assert timed_out.get_json()["error"] == "render_timeout"
    assert at_capacity.status_code == 503
    assert at_capacity.get_json()["error"] == "capacity_unavailable"
