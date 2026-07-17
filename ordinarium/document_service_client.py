import requests
from flask import current_app


class DocumentServiceError(RuntimeError):
    pass


def render_document(export_format, payload):
    service_url = current_app.config.get("DOCUMENT_SERVICE_URL")
    if not service_url:
        raise DocumentServiceError("Document service is not configured.")

    try:
        response = requests.post(
            service_url,
            json={"format": export_format, **payload},
            timeout=current_app.config["DOCUMENT_SERVICE_TIMEOUT_SECONDS"],
        )
    except requests.RequestException as exc:
        raise DocumentServiceError("Document service is unavailable.") from exc

    if response.status_code != 200:
        raise DocumentServiceError(
            f"Document service returned HTTP {response.status_code}."
        )
    if len(response.content) > current_app.config["DOCUMENT_SERVICE_MAX_BYTES"]:
        raise DocumentServiceError("Document service response exceeded the size limit.")

    current_app.logger.info(
        "Document service rendered %s bytes=%s render_ms=%s peak_rss_kib=%s",
        export_format,
        len(response.content),
        response.headers.get("X-Ordinarium-Render-Ms", "unknown"),
        response.headers.get("X-Ordinarium-Peak-Rss-Kib", "unknown"),
    )
    return response.content
