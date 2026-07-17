from types import SimpleNamespace

import pytest
import requests

from ordinarium.document_service_client import DocumentServiceError, render_document


def _response(status_code=200, content=b"rendered", headers=None):
    return SimpleNamespace(
        status_code=status_code,
        content=content,
        headers=headers or {},
    )


def test_render_document_posts_internal_payload(app, monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(url=url, json=json, timeout=timeout)
        return _response(headers={"X-Ordinarium-Render-Ms": "12.5"})

    monkeypatch.setattr(requests, "post", fake_post)
    app.config.update(
        DOCUMENT_SERVICE_URL="http://documents.internal/render",
        DOCUMENT_SERVICE_TIMEOUT_SECONDS=15,
    )

    with app.app_context():
        content = render_document("pdf", {"html": "<p>ok</p>"})

    assert content == b"rendered"
    assert captured == {
        "url": "http://documents.internal/render",
        "json": {"format": "pdf", "html": "<p>ok</p>"},
        "timeout": 15,
    }


def test_render_document_translates_transport_failure(app, monkeypatch):
    def fail_request(*_args, **_kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "post", fail_request)
    app.config["DOCUMENT_SERVICE_URL"] = "http://documents.internal/render"

    with app.app_context(), pytest.raises(DocumentServiceError, match="unavailable"):
        render_document("docx", {"context": {}})


def test_render_document_rejects_failed_or_oversized_response(app, monkeypatch):
    app.config.update(
        DOCUMENT_SERVICE_URL="http://documents.internal/render",
        DOCUMENT_SERVICE_MAX_BYTES=4,
    )

    monkeypatch.setattr(requests, "post", lambda *_args, **_kwargs: _response(503))
    with app.app_context(), pytest.raises(DocumentServiceError, match="HTTP 503"):
        render_document("pdf", {"html": ""})

    monkeypatch.setattr(
        requests, "post", lambda *_args, **_kwargs: _response(content=b"12345")
    )
    with app.app_context(), pytest.raises(DocumentServiceError, match="size limit"):
        render_document("pdf", {"html": ""})
