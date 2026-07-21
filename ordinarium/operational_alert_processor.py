from __future__ import annotations

from email.utils import parseaddr
from urllib.parse import urlparse

import requests
from flask import current_app


MAILERSEND_URL = "https://api.mailersend.com/v1/email"
MAX_RETRY_DELAY_SECONDS = 3600

ALERT_TITLES = {
    "worker_runtime_failure": "Worker runtime failure",
    "worker_request_failure": "Worker request failure",
    "container_started": "Container started",
    "container_failure": "Container failure",
    "d1_failure": "D1 operation failure",
    "queue_failure": "Queue operation failure",
    "queue_backlog": "Queue backlog threshold exceeded",
    "dead_letter": "Dead-letter queue contains messages",
    "export_failure": "Document export failure",
    "pco_authorization_failure": "Planning Center authorization failure",
    "edge_security_failure": "Edge security failure",
}

SOURCE_KEYS = {
    "script_name",
    "container_role",
    "queue",
    "route",
    "status",
    "error_category",
    "request_id",
    "job_id",
}


def valid_operational_alert(payload):
    if not isinstance(payload, dict) or set(payload) != {
        "alert_id",
        "kind",
        "severity",
        "occurred_at",
        "source",
    }:
        return False
    if not _valid_identifier(payload["alert_id"]):
        return False
    if payload["kind"] not in ALERT_TITLES:
        return False
    if payload["severity"] not in {"warning", "critical"}:
        return False
    if not isinstance(payload["occurred_at"], str) or not (
        1 <= len(payload["occurred_at"]) <= 32
    ):
        return False
    source = payload["source"]
    if not isinstance(source, dict) or set(source) != SOURCE_KEYS:
        return False
    if not _valid_identifier(source["script_name"]):
        return False
    for key in {
        "container_role",
        "queue",
        "error_category",
        "request_id",
        "job_id",
    }:
        if source[key] is not None and not _valid_identifier(source[key]):
            return False
    if source["route"] is not None and not (
        isinstance(source["route"], str) and len(source["route"]) <= 256
    ):
        return False
    return source["status"] is None or (
        isinstance(source["status"], int)
        and not isinstance(source["status"], bool)
        and 100 <= source["status"] <= 599
    )


def process_operational_alert(payload):
    try:
        delivery = _delivery_config()
    except ValueError as exc:
        return _retry_response(str(exc), 300)

    response = _send_mailersend(delivery, _mailersend_payload(payload, delivery))
    if 200 <= response.status_code < 300:
        return _terminal_response("accepted")
    if response.status_code == 429 or response.status_code >= 500:
        return _retry_response(
            "provider_unavailable", _retry_after(response, default=60)
        )
    return _terminal_response("provider_rejected")


def _delivery_config():
    deployment_environment = str(current_app.config.get("DEPLOYMENT_ENV", "")).lower()
    side_effects_enabled = _config_bool(
        current_app.config.get("EXTERNAL_SIDE_EFFECTS_ENABLED")
    )
    origin = str(current_app.config.get("APP_ORIGIN") or "").rstrip("/")
    expected_hostname = str(
        current_app.config.get("SIDE_EFFECTS_HOSTNAME") or ""
    ).lower()
    parsed_origin = urlparse(origin)
    if deployment_environment not in {"staging", "production"}:
        raise ValueError("side_effect_environment_invalid")
    if not side_effects_enabled:
        raise ValueError("side_effects_disabled")
    if (
        parsed_origin.scheme != "https"
        or not parsed_origin.hostname
        or parsed_origin.hostname.lower() != expected_hostname
    ):
        raise ValueError("app_origin_invalid")

    api_token = current_app.config.get("MAILERSEND_API_TOKEN")
    from_email = current_app.config.get("MAILERSEND_FROM_EMAIL")
    recipient = str(current_app.config.get("ALERT_EMAIL_TO") or "").strip()
    if not api_token or not from_email:
        raise ValueError("provider_configuration_missing")
    if not _valid_email_address(recipient):
        raise ValueError("alert_recipient_invalid")
    return {
        "api_token": api_token,
        "from_email": from_email,
        "from_name": current_app.config.get("MAILERSEND_FROM_NAME") or "Ordinarium",
        "recipient": recipient,
        "environment": deployment_environment,
    }


def _mailersend_payload(alert, delivery):
    title = ALERT_TITLES[alert["kind"]]
    severity = alert["severity"].upper()
    source_lines = [
        f"Environment: {delivery['environment']}",
        f"Severity: {severity}",
        f"Event: {title}",
        f"Occurred at: {alert['occurred_at']}",
        f"Alert ID: {alert['alert_id']}",
    ]
    labels = {
        "script_name": "Worker",
        "container_role": "Container role",
        "queue": "Queue",
        "route": "Route",
        "status": "Status",
        "error_category": "Error category",
        "request_id": "Request ID",
        "job_id": "Job ID",
    }
    for key, label in labels.items():
        value = alert["source"].get(key)
        if value is not None:
            source_lines.append(f"{label}: {value}")
    source_lines.extend(
        [
            "",
            "This message contains sanitized operational metadata only.",
        ]
    )
    return {
        "from": {
            "email": delivery["from_email"],
            "name": delivery["from_name"],
        },
        "to": [{"email": delivery["recipient"], "name": "Ryan Willers"}],
        "subject": f"[Ordinarium {delivery['environment']}] {severity}: {title}",
        "text": "\n".join(source_lines),
    }


def _send_mailersend(delivery, payload):
    transport = current_app.config.get("MAILERSEND_TRANSPORT")
    request_options = {
        "headers": {
            "Authorization": f"Bearer {delivery['api_token']}",
            "Content-Type": "application/json",
        },
        "json": payload,
        "timeout": 20,
    }
    try:
        if transport:
            return transport(MAILERSEND_URL, **request_options)
        return requests.post(MAILERSEND_URL, **request_options)
    except requests.RequestException:
        return _UnavailableResponse()


def _retry_after(response, default):
    try:
        seconds = int(response.headers.get("Retry-After", default))
    except (TypeError, ValueError):
        seconds = default
    return max(1, min(seconds, MAX_RETRY_DELAY_SECONDS))


def _valid_email_address(value):
    parsed_name, parsed_address = parseaddr(value)
    return not parsed_name and parsed_address == value and "@" in parsed_address


def _valid_identifier(value):
    return (
        isinstance(value, str)
        and 0 < len(value) <= 128
        and all(character.isalnum() or character in "._:@+-" for character in value)
    )


def _config_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _terminal_response(reason):
    return {"disposition": "terminal", "persisted": True, "reason": reason}, 200


def _retry_response(reason, retry_after_seconds):
    return {
        "error": reason,
        "retry_after_seconds": retry_after_seconds,
    }, 503


class _UnavailableResponse:
    status_code = 503
    headers = {}
