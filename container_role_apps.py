import os
import resource
import time

from flask import Flask, Response, jsonify, request

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
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

    @app.post("/render")
    def render_document():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "invalid_json"}), 400

        export_format = payload.get("format")
        started_at = time.perf_counter()
        try:
            content, mimetype = _render_payload(export_format, payload)
        except (KeyError, TypeError, ValueError) as exc:
            return jsonify({"error": "invalid_payload", "message": str(exc)}), 400
        except RuntimeError as exc:
            app.logger.exception("Document rendering failed")
            return jsonify({"error": "render_failed", "message": str(exc)}), 503

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


def _elapsed_ms(started_at):
    return (time.perf_counter() - started_at) * 1000


def _peak_rss_kib():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
