from __future__ import annotations

import json

import requests
from flask import current_app


class QueuePublicationError(RuntimeError):
    """Base error for a queue publication that did not complete."""


class QueuePublicationNotConfigured(QueuePublicationError):
    """Queue publishing is disabled for this application environment."""


class QueuePublicationRejected(QueuePublicationError):
    """The internal queue service rejected a caller contract violation."""


class QueuePublicationUnavailable(QueuePublicationError):
    """The internal queue service could not durably accept a message."""


def publish_pco_row(*, job_id, row_id, user_id):
    payload = {
        "job_id": _identifier(job_id, "job_id"),
        "row_id": _identifier(row_id, "row_id"),
        "user_id": _positive_integer(user_id, "user_id"),
    }
    _publish("pco", payload)


def publish_password_reset(*, reset_id):
    _publish("email", {"reset_id": _identifier(reset_id, "reset_id")})


def queue_publishing_is_configured():
    return bool(current_app.config.get("QUEUE_SERVICE_URL"))


def _publish(route, payload):
    service_url = current_app.config.get("QUEUE_SERVICE_URL")
    if not service_url:
        raise QueuePublicationNotConfigured("Queue publishing is not configured.")

    request_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    try:
        response = requests.post(
            f"{service_url.rstrip('/')}/{route}",
            data=request_body,
            headers={"Content-Type": "application/json"},
            timeout=current_app.config["QUEUE_SERVICE_TIMEOUT_SECONDS"],
        )
    except requests.RequestException as exc:
        raise QueuePublicationUnavailable("Queue service is unavailable.") from exc

    try:
        if response.status_code == 202:
            return
        if 400 <= response.status_code < 500:
            raise QueuePublicationRejected(
                f"Queue service rejected the message with HTTP {response.status_code}."
            )
        raise QueuePublicationUnavailable(
            f"Queue service returned HTTP {response.status_code}."
        )
    finally:
        response.close()


def _identifier(value, field_name):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise QueuePublicationRejected(f"{field_name} must be a non-empty identifier.")
    return value


def _positive_integer(value, field_name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise QueuePublicationRejected(f"{field_name} must be a positive integer.")
    return value
