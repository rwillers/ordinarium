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
    app = _create_private_container_app("jobs")
    app.config.update(
        MAX_CONTENT_LENGTH=int(os.environ.get("JOB_MAX_REQUEST_BYTES", "1024")),
        JOB_SERVICE_AUTH_TOKEN=os.environ.get("JOB_SERVICE_AUTH_TOKEN"),
        ORDINARIUM_CONTAINER_ROLE=os.environ.get("ORDINARIUM_CONTAINER_ROLE", "jobs"),
        DATABASE_GATEWAY_BACKEND=os.environ.get("DATABASE_GATEWAY_BACKEND", "sqlite"),
        D1_SERVICE_URL=os.environ.get("D1_SERVICE_URL"),
        D1_SERVICE_TIMEOUT_SECONDS=float(
            os.environ.get("D1_SERVICE_TIMEOUT_SECONDS", "20")
        ),
        D1_SERVICE_MAX_BYTES=int(
            os.environ.get("D1_SERVICE_MAX_BYTES", str(5 * 1024 * 1024))
        ),
        PCO_API_BASE=os.environ.get(
            "PCO_API_BASE", "https://api.planningcenteronline.com"
        ),
        PCO_OAUTH_TOKEN_URL=os.environ.get(
            "PCO_OAUTH_TOKEN_URL",
            "https://api.planningcenteronline.com/oauth/token",
        ),
        PCO_CLIENT_ID=os.environ.get("PCO_CLIENT_ID"),
        PCO_CLIENT_SECRET=os.environ.get("PCO_CLIENT_SECRET"),
        PCO_TOKEN_ENCRYPTION_KEYS=os.environ.get("PCO_TOKEN_ENCRYPTION_KEYS"),
        PCO_TOKEN_ENCRYPTION_PRIMARY_VERSION=os.environ.get(
            "PCO_TOKEN_ENCRYPTION_PRIMARY_VERSION", "v1"
        ),
        DEPLOYMENT_ENV=os.environ.get("DEPLOYMENT_ENV"),
        APP_ORIGIN=os.environ.get("APP_ORIGIN"),
        EXTERNAL_SIDE_EFFECTS_ENABLED=os.environ.get(
            "EXTERNAL_SIDE_EFFECTS_ENABLED", "false"
        ),
        SIDE_EFFECTS_HOSTNAME=os.environ.get("SIDE_EFFECTS_HOSTNAME"),
        MAILERSEND_API_TOKEN=os.environ.get("MAILERSEND_API_TOKEN"),
        MAILERSEND_FROM_EMAIL=os.environ.get("MAILERSEND_FROM_EMAIL"),
        MAILERSEND_FROM_NAME=os.environ.get("MAILERSEND_FROM_NAME", "Ordinarium"),
        PASSWORD_RESET_DELIVERY_KEY=os.environ.get("PASSWORD_RESET_DELIVERY_KEY"),
        ALERT_EMAIL_TO=os.environ.get("ALERT_EMAIL_TO"),
    )
    if app.config["ORDINARIUM_CONTAINER_ROLE"] == "pco-jobs":
        _configure_pco_jobs_app(app)
    elif app.config["ORDINARIUM_CONTAINER_ROLE"] == "email-jobs":
        _configure_email_jobs_app(app)

    @app.errorhandler(RequestEntityTooLarge)
    def job_request_too_large(_error):
        return jsonify({"error": "request_too_large"}), 413

    @app.post("/jobs/pco/rows/process")
    def process_pco_row():
        rejected = _validate_job_request(app, "pco-jobs", _valid_pco_job_payload)
        if rejected:
            return rejected
        if not app.config.get("D1_SERVICE_URL") and not app.config.get(
            "DATABASE_GATEWAY_FACTORY"
        ):
            return _processor_unavailable_response()
        from ordinarium.pco_job_processor import process_pco_row_message

        body, status = process_pco_row_message(request.get_json())
        response = jsonify(body)
        response.status_code = status
        if status in {429, 503}:
            response.headers["Retry-After"] = str(body["retry_after_seconds"])
        return response

    @app.post("/jobs/pco/rows/dead-letter")
    def dead_letter_pco_row():
        rejected = _validate_job_request(app, "pco-jobs", _valid_pco_job_payload)
        if rejected:
            return rejected
        from ordinarium.pco_job_processor import dead_letter_pco_row_message

        body, status = dead_letter_pco_row_message(request.get_json())
        response = jsonify(body)
        response.status_code = status
        if status == 503:
            response.headers["Retry-After"] = str(body["retry_after_seconds"])
        return response

    @app.post("/jobs/email/resets/process")
    def process_email_reset():
        rejected = _validate_job_request(app, "email-jobs", _valid_email_job_payload)
        if rejected:
            return rejected
        if not app.config.get("D1_SERVICE_URL") and not app.config.get(
            "DATABASE_GATEWAY_FACTORY"
        ):
            return _processor_unavailable_response()
        from ordinarium.password_reset_email_processor import (
            process_password_reset_message,
        )

        body, status = process_password_reset_message(request.get_json())
        response = jsonify(body)
        response.status_code = status
        if status in {429, 503}:
            response.headers["Retry-After"] = str(body["retry_after_seconds"])
        return response

    @app.post("/jobs/email/resets/dead-letter")
    def dead_letter_email_reset():
        rejected = _validate_job_request(app, "email-jobs", _valid_email_job_payload)
        if rejected:
            return rejected
        if not app.config.get("D1_SERVICE_URL") and not app.config.get(
            "DATABASE_GATEWAY_FACTORY"
        ):
            return _processor_unavailable_response()
        from ordinarium.password_reset_email_processor import (
            dead_letter_password_reset_message,
        )

        body, status = dead_letter_password_reset_message(request.get_json())
        response = jsonify(body)
        response.status_code = status
        return response

    @app.post("/jobs/email/alerts/process")
    def process_email_alert():
        from ordinarium.operational_alert_processor import (
            process_operational_alert,
            valid_operational_alert,
        )

        rejected = _validate_job_request(app, "email-jobs", valid_operational_alert)
        if rejected:
            return rejected
        body, status = process_operational_alert(request.get_json())
        response = jsonify(body)
        response.status_code = status
        if status == 503:
            response.headers["Retry-After"] = str(body["retry_after_seconds"])
        return response

    return app


def _unavailable_job_response(app, expected_role, payload_validator):
    rejected = _validate_job_request(app, expected_role, payload_validator)
    if rejected:
        return rejected
    return _processor_unavailable_response()


def _processor_unavailable_response():
    response = jsonify({"error": "processor_unavailable", "retry_after_seconds": 30})
    response.status_code = 503
    response.headers["Retry-After"] = "30"
    return response


def _validate_job_request(app, expected_role, payload_validator):
    if not _job_request_is_authorized(app, expected_role):
        return jsonify({"error": "not_found"}), 404
    if not payload_validator(request.get_json(silent=True)):
        return jsonify({"error": "invalid_payload"}), 400
    return None


def _configure_pco_jobs_app(app):
    import markdown2
    from markupsafe import Markup

    from ordinarium.db import close_db

    app.jinja_env.filters["markdown"] = lambda value: Markup(
        markdown2.markdown(
            value or "",
            extras=["fenced-code-blocks", "code-friendly", "markdown-in-html"],
        )
    )
    app.teardown_appcontext(close_db)


def _configure_email_jobs_app(app):
    from ordinarium.db import close_db

    app.teardown_appcontext(close_db)


def _job_request_is_authorized(app, expected_role):
    if app.config.get("ORDINARIUM_CONTAINER_ROLE") != expected_role:
        return False
    expected_token = app.config.get("JOB_SERVICE_AUTH_TOKEN")
    provided_token = request.headers.get("X-Ordinarium-Job-Auth")
    if not expected_token or not provided_token:
        return False
    return hmac.compare_digest(provided_token, expected_token)


def _valid_pco_job_payload(payload):
    if not _has_exact_keys(payload, {"job_id", "row_id", "user_id"}):
        return False
    return (
        _valid_identifier(payload["job_id"])
        and _valid_identifier(payload["row_id"])
        and isinstance(payload["user_id"], int)
        and not isinstance(payload["user_id"], bool)
        and payload["user_id"] > 0
    )


def _valid_email_job_payload(payload):
    return _has_exact_keys(payload, {"reset_id"}) and _valid_identifier(
        payload["reset_id"]
    )


def _has_exact_keys(payload, expected_keys):
    return isinstance(payload, dict) and set(payload) == expected_keys


def _valid_identifier(value):
    return isinstance(value, str) and 0 < len(value) <= 128


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
