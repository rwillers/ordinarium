import json

import pytest
import requests

from ordinarium import queue_publisher


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code
        self.closed = False

    def close(self):
        self.closed = True


def test_pco_publisher_sends_only_row_identifiers(app, monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse(202)

    monkeypatch.setattr(queue_publisher.requests, "post", fake_post)
    with app.app_context():
        app.config.update(
            QUEUE_SERVICE_URL="http://queue.internal",
            QUEUE_SERVICE_TIMEOUT_SECONDS=3,
        )
        queue_publisher.publish_pco_row(job_id="job-1", row_id="row-1", user_id=7)

    assert captured["url"] == "http://queue.internal/pco"
    assert json.loads(captured["data"]) == {
        "job_id": "job-1",
        "row_id": "row-1",
        "user_id": 7,
    }
    assert set(captured["headers"]) == {"Content-Type"}
    assert captured["timeout"] == 3


def test_email_publisher_sends_only_opaque_reset_id(app, monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse(202)

    monkeypatch.setattr(queue_publisher.requests, "post", fake_post)
    with app.app_context():
        app.config["QUEUE_SERVICE_URL"] = "http://queue.internal/"
        queue_publisher.publish_password_reset(reset_id="reset-1")

    assert captured["url"] == "http://queue.internal/email"
    assert json.loads(captured["data"]) == {"reset_id": "reset-1"}
    assert "token" not in captured["data"].decode()


def test_publisher_is_explicitly_disabled_without_service_url(app):
    with app.app_context():
        app.config["QUEUE_SERVICE_URL"] = None

        assert queue_publisher.queue_publishing_is_configured() is False
        with pytest.raises(queue_publisher.QueuePublicationNotConfigured):
            queue_publisher.publish_password_reset(reset_id="reset-1")


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (400, queue_publisher.QueuePublicationRejected),
        (503, queue_publisher.QueuePublicationUnavailable),
    ],
)
def test_publisher_classifies_http_failures(app, monkeypatch, status_code, error_type):
    response = FakeResponse(status_code)
    monkeypatch.setattr(
        queue_publisher.requests, "post", lambda *_args, **_kwargs: response
    )

    with app.app_context():
        app.config["QUEUE_SERVICE_URL"] = "http://queue.internal"
        with pytest.raises(error_type):
            queue_publisher.publish_password_reset(reset_id="reset-1")

    assert response.closed is True


def test_publisher_classifies_transport_failures(app, monkeypatch):
    def fail(*_args, **_kwargs):
        raise requests.Timeout("timeout")

    monkeypatch.setattr(queue_publisher.requests, "post", fail)
    with app.app_context():
        app.config["QUEUE_SERVICE_URL"] = "http://queue.internal"
        with pytest.raises(queue_publisher.QueuePublicationUnavailable):
            queue_publisher.publish_password_reset(reset_id="reset-1")


def test_publisher_rejects_secrets_and_invalid_identifiers_before_http(app):
    with app.app_context():
        app.config["QUEUE_SERVICE_URL"] = "http://queue.internal"
        with pytest.raises(queue_publisher.QueuePublicationRejected):
            queue_publisher.publish_pco_row(
                job_id="job-1", row_id="row-1", user_id="oauth-secret"
            )
