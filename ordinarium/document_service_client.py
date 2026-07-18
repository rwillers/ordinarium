import json
import secrets

import requests
from flask import current_app


class DocumentServiceError(RuntimeError):
    pass


def render_document(export_format, payload):
    service_url = current_app.config.get("DOCUMENT_SERVICE_URL")
    if not service_url:
        raise DocumentServiceError("Document service is not configured.")

    request_payload = {"format": export_format, **payload}
    request_body = json.dumps(
        request_payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    if len(request_body) > current_app.config["DOCUMENT_SERVICE_MAX_REQUEST_BYTES"]:
        raise DocumentServiceError("Document service request exceeded the size limit.")

    try:
        response = requests.post(
            service_url,
            data=request_body,
            headers={
                "Content-Type": "application/json",
                "X-Ordinarium-Request-Id": secrets.token_hex(16),
            },
            timeout=current_app.config["DOCUMENT_SERVICE_TIMEOUT_SECONDS"],
            stream=True,
        )
    except requests.RequestException as exc:
        raise DocumentServiceError("Document service is unavailable.") from exc

    if response.status_code != 200:
        _close_response(response)
        raise DocumentServiceError(
            f"Document service returned HTTP {response.status_code}."
        )
    try:
        content = _read_bounded_response(
            response, current_app.config["DOCUMENT_SERVICE_MAX_BYTES"]
        )
    except requests.RequestException as exc:
        raise DocumentServiceError("Document service is unavailable.") from exc
    finally:
        _close_response(response)

    current_app.logger.info(
        "Document service rendered %s bytes=%s render_ms=%s peak_rss_kib=%s",
        export_format,
        len(content),
        response.headers.get("X-Ordinarium-Render-Ms", "unknown"),
        response.headers.get("X-Ordinarium-Peak-Rss-Kib", "unknown"),
    )
    return content


def _read_bounded_response(response, max_bytes):
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise DocumentServiceError(
                    "Document service response exceeded the size limit."
                )
        except ValueError:
            pass

    content = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        content.extend(chunk)
        if len(content) > max_bytes:
            raise DocumentServiceError(
                "Document service response exceeded the size limit."
            )
    return bytes(content)


def _close_response(response):
    close = getattr(response, "close", None)
    if close:
        close()
