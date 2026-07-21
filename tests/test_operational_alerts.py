from types import SimpleNamespace

from container_role_apps import create_jobs_app
from ordinarium.operational_alert_processor import valid_operational_alert


def _alert():
    return {
        "alert_id": "alert-1",
        "kind": "d1_failure",
        "severity": "critical",
        "occurred_at": "2026-07-21T12:00:00.000Z",
        "source": {
            "script_name": "ordinarium-app-staging",
            "container_role": "d1-bridge",
            "queue": None,
            "route": "/service/:id",
            "status": 503,
            "error_category": "internal",
            "request_id": "request-1",
            "job_id": None,
        },
    }


def _email_app(monkeypatch, transport):
    monkeypatch.setenv("ORDINARIUM_CONTAINER_ROLE", "email-jobs")
    monkeypatch.setenv("JOB_SERVICE_AUTH_TOKEN", "email-secret")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    monkeypatch.setenv("APP_ORIGIN", "https://containers-staging.ordinarium.com")
    monkeypatch.setenv("SIDE_EFFECTS_HOSTNAME", "containers-staging.ordinarium.com")
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECTS_ENABLED", "true")
    monkeypatch.setenv("MAILERSEND_API_TOKEN", "provider-secret")
    monkeypatch.setenv("MAILERSEND_FROM_EMAIL", "alerts@ordinarium.com")
    monkeypatch.setenv("ALERT_EMAIL_TO", "ryanwillers+ordo@gmail.com")
    app = create_jobs_app()
    app.config["MAILERSEND_TRANSPORT"] = transport
    return app


def test_operational_alert_contract_rejects_extra_or_unbounded_fields():
    alert = _alert()
    assert valid_operational_alert(alert)
    assert not valid_operational_alert({**alert, "exception": "secret"})
    assert not valid_operational_alert(
        {**alert, "source": {**alert["source"], "raw_error": "secret"}}
    )


def test_email_alert_endpoint_sends_only_sanitized_operational_metadata(monkeypatch):
    captured = {}

    def transport(url, **kwargs):
        captured.update(url=url, **kwargs)
        return SimpleNamespace(status_code=202, headers={})

    client = _email_app(monkeypatch, transport).test_client()
    response = client.post(
        "/jobs/email/alerts/process",
        json=_alert(),
        headers={"X-Ordinarium-Job-Auth": "email-secret"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "disposition": "terminal",
        "persisted": True,
        "reason": "accepted",
    }
    assert captured["json"]["to"] == [
        {"email": "ryanwillers+ordo@gmail.com", "name": "Ryan Willers"}
    ]
    assert "D1 operation failure" in captured["json"]["subject"]
    assert "request-1" in captured["json"]["text"]
    assert captured["headers"]["Authorization"] == "Bearer provider-secret"


def test_email_alert_endpoint_retries_provider_outages(monkeypatch):
    def transport(_url, **_kwargs):
        return SimpleNamespace(status_code=429, headers={"Retry-After": "75"})

    client = _email_app(monkeypatch, transport).test_client()
    response = client.post(
        "/jobs/email/alerts/process",
        json=_alert(),
        headers={"X-Ordinarium-Job-Auth": "email-secret"},
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "75"
    assert response.get_json() == {
        "error": "provider_unavailable",
        "retry_after_seconds": 75,
    }


def test_email_alert_endpoint_is_private_and_role_gated(monkeypatch):
    monkeypatch.setenv("ORDINARIUM_CONTAINER_ROLE", "pco-jobs")
    monkeypatch.setenv("JOB_SERVICE_AUTH_TOKEN", "pco-secret")
    response = (
        create_jobs_app()
        .test_client()
        .post(
            "/jobs/email/alerts/process",
            json=_alert(),
            headers={"X-Ordinarium-Job-Auth": "pco-secret"},
        )
    )

    assert response.status_code == 404
