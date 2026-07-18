import hmac
import os
import resource
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from document_rendering import render_docx_bytes, render_pdf_bytes


def _create_private_container_app(default_role):
    app = Flask(f"ordinarium.{default_role}")
    role = os.environ.get("ORDINARIUM_CONTAINER_ROLE", default_role)

    @app.get("/health")
    def health():
        return jsonify({"role": role, "status": "ok"})

    return app


def create_documents_app():
    app = _create_private_container_app("documents")
    app.config.update(
        MAX_CONTENT_LENGTH=int(
            os.environ.get("DOCUMENT_MAX_REQUEST_BYTES", str(5 * 1024 * 1024))
        ),
        DOCUMENT_MAX_OUTPUT_BYTES=int(
            os.environ.get("DOCUMENT_MAX_OUTPUT_BYTES", str(25 * 1024 * 1024))
        ),
        DOCUMENT_RENDER_TIMEOUT_SECONDS=float(
            os.environ.get("DOCUMENT_RENDER_TIMEOUT_SECONDS", "60")
        ),
        DOCUMENT_SERVICE_AUTH_TOKEN=os.environ.get("DOCUMENT_SERVICE_AUTH_TOKEN"),
    )
    render_slot = threading.BoundedSemaphore(value=1)
    render_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="document")

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        return jsonify({"error": "request_too_large"}), 413

    @app.post("/render")
    def render_document():
        if not _document_request_is_authorized(app):
            return jsonify({"error": "not_found"}), 404
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "invalid_json"}), 400
        if not render_slot.acquire(blocking=False):
            return jsonify({"error": "capacity_unavailable"}), 503

        export_format = payload.get("format")
        started_at = time.perf_counter()
        release_slot = True
        try:
            future = render_executor.submit(_render_payload, export_format, payload)
            content, mimetype = future.result(
                timeout=app.config["DOCUMENT_RENDER_TIMEOUT_SECONDS"]
            )
            if len(content) > app.config["DOCUMENT_MAX_OUTPUT_BYTES"]:
                raise RuntimeError("Rendered document exceeded the output size limit.")
        except FutureTimeoutError:
            release_slot = False
            future.add_done_callback(lambda _future: render_slot.release())
            app.logger.error("Document rendering exceeded its execution deadline")
            return jsonify({"error": "render_timeout"}), 503
        except (KeyError, TypeError, ValueError) as exc:
            return jsonify({"error": "invalid_payload", "message": str(exc)}), 400
        except RuntimeError as exc:
            app.logger.exception("Document rendering failed")
            return jsonify({"error": "render_failed", "message": str(exc)}), 503
        finally:
            if release_slot:
                render_slot.release()

        response = Response(content, mimetype=mimetype)
        response.headers["Content-Length"] = str(len(content))
        response.headers["X-Ordinarium-Render-Ms"] = f"{_elapsed_ms(started_at):.1f}"
        response.headers["X-Ordinarium-Peak-Rss-Kib"] = str(_peak_rss_kib())
        return response

    return app


def create_jobs_app():
    return _create_private_container_app("jobs")


def _render_payload(export_format, payload):
    if export_format == "pdf":
        html_text = payload["html"]
        if not isinstance(html_text, str):
            raise TypeError("html must be a string")
        return (
            render_pdf_bytes(html_text, base_url="/app/ordinarium"),
            "application/pdf",
        )

    if export_format == "docx":
        context = payload["context"]
        if not isinstance(context, dict):
            raise TypeError("context must be an object")
        mimetype = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        return render_docx_bytes(context), mimetype

    raise ValueError("format must be pdf or docx")


def _document_request_is_authorized(app):
    expected_token = app.config.get("DOCUMENT_SERVICE_AUTH_TOKEN")
    provided_token = request.headers.get("X-Ordinarium-Document-Auth")
    if not expected_token or not provided_token:
        return False
    return hmac.compare_digest(provided_token, expected_token)


def _elapsed_ms(started_at):
    return (time.perf_counter() - started_at) * 1000


def _peak_rss_kib():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
