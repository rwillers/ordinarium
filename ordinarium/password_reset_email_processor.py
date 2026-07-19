from __future__ import annotations

import time
import secrets
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime, parseaddr
from urllib.parse import urlparse

import requests
from flask import current_app

from .db import get_database_gateway
from .password_reset_store import (
    PasswordResetConfigurationError,
    PasswordResetEnvelopeError,
    decrypt_delivery_token,
)


MAILERSEND_URL = "https://api.mailersend.com/v1/email"
DELIVERY_LEASE_SECONDS = 240
MAX_RETRY_DELAY_SECONDS = 3600
TERMINAL_DELIVERY_STATUSES = {"sent", "accepted", "suppressed", "failed"}


class EmailDeliveryTransientError(RuntimeError):
    def __init__(self, category, retry_after_seconds):
        super().__init__(category)
        self.category = category
        self.retry_after_seconds = max(
            1, min(int(retry_after_seconds), MAX_RETRY_DELAY_SECONDS)
        )


class EmailDeliveryTerminalError(RuntimeError):
    def __init__(self, category):
        super().__init__(category)
        self.category = category


def process_password_reset_message(payload, *, now_epoch=None):
    reset_id = payload["reset_id"]
    now_epoch = int(time.time() if now_epoch is None else now_epoch)
    gateway = get_database_gateway()
    existing = _load_delivery(gateway, reset_id)
    if existing is None:
        return _terminal_response("not_found")
    terminal_category = _preclaim_terminal_category(existing, now_epoch)
    if terminal_category:
        if existing["delivery_status"] not in TERMINAL_DELIVERY_STATUSES:
            _terminalize(gateway, reset_id, terminal_category)
        return _terminal_response(terminal_category)

    claim_token = _claim_delivery(gateway, reset_id, now_epoch)
    if claim_token is None:
        current = _load_delivery(gateway, reset_id)
        if current is None:
            return _terminal_response("not_found")
        terminal_category = _preclaim_terminal_category(current, now_epoch)
        if terminal_category:
            if current["delivery_status"] not in TERMINAL_DELIVERY_STATUSES:
                _terminalize(gateway, reset_id, terminal_category)
            return _terminal_response(terminal_category)
        retry_after = max(
            1,
            min(
                int(current.get("delivery_claim_expires_at") or now_epoch + 30)
                - now_epoch,
                MAX_RETRY_DELAY_SECONDS,
            ),
        )
        return _retry_response("delivery_in_progress", retry_after)

    row = gateway.fetch_one(
        """
        select r.*, u.email, u.first_name, u.last_name, u.deleted_at
        from password_reset_requests r
        join users u on u.id=r.user_id
        where r.id=? and r.delivery_claim_token=?
        limit 1
        """,
        (reset_id, claim_token),
    )
    if row is None:
        return _retry_response("claim_lost", 30)

    try:
        delivery_config = _delivery_config()
        _validate_recipient(row)
        if not row.get("delivery_token_envelope"):
            raise EmailDeliveryTerminalError("delivery_material_missing")
        token = decrypt_delivery_token(reset_id, row["delivery_token_envelope"])
        response = _send_mailersend(
            delivery_config,
            _mailersend_payload(row, token, delivery_config["origin"]),
        )
        status_code = int(response.status_code)
        if status_code == 429:
            raise EmailDeliveryTransientError(
                "provider_rate_limit",
                _retry_after(response, int(row["delivery_attempts"])),
            )
        if status_code >= 500:
            raise EmailDeliveryTransientError(
                "provider_unavailable",
                _retry_after(response, int(row["delivery_attempts"])),
            )
        if status_code >= 400:
            category = (
                "provider_auth"
                if status_code in {401, 403}
                else f"provider_rejected_{status_code}"
            )
            raise EmailDeliveryTerminalError(category)
        if not 200 <= status_code < 300:
            raise EmailDeliveryTerminalError("provider_invalid_response")
        provider_id = response.headers.get("x-message-id")
        if status_code == 202:
            delivery_status = "sent" if provider_id else "suppressed"
        else:
            delivery_status = "accepted"
        mutation = gateway.execute(
            """
            update password_reset_requests
            set delivery_status=?,
                delivery_provider_id=?,
                sent_at=CURRENT_TIMESTAMP,
                delivery_token_envelope=null,
                delivery_claim_token=null,
                delivery_claim_expires_at=null,
                delivery_last_error=null,
                delivery_updated_at=CURRENT_TIMESTAMP
            where id=? and delivery_status='sending'
              and delivery_claim_token=?
            """,
            (delivery_status, provider_id, reset_id, claim_token),
        )
        if mutation.changes != 1:
            # MailerSend does not expose an idempotency key for this endpoint.
            # Retrying after acceptance but before this write can duplicate email.
            return _retry_response("success_persistence_uncertain", 30)
        return _terminal_response(delivery_status, provider_id=provider_id)
    except requests.RequestException:
        return _persist_retry(gateway, reset_id, claim_token, "network", _backoff(row))
    except EmailDeliveryTransientError as exc:
        return _persist_retry(
            gateway,
            reset_id,
            claim_token,
            exc.category,
            exc.retry_after_seconds,
        )
    except (PasswordResetConfigurationError, PasswordResetEnvelopeError):
        if _fail_claimed_delivery(
            gateway, reset_id, claim_token, "crypto_configuration"
        ):
            return _terminal_response("crypto_configuration")
        return _retry_response("terminal_persistence_uncertain", 30)
    except EmailDeliveryTerminalError as exc:
        if _fail_claimed_delivery(gateway, reset_id, claim_token, exc.category):
            return _terminal_response(exc.category)
        return _retry_response("terminal_persistence_uncertain", 30)
    except Exception:
        return _persist_retry(gateway, reset_id, claim_token, "internal", 30)


def dead_letter_password_reset_message(payload):
    reset_id = payload["reset_id"]
    _terminalize(get_database_gateway(), reset_id, "retry_exhausted")
    return _terminal_response("retry_exhausted")


def _load_delivery(gateway, reset_id):
    return gateway.fetch_one(
        """
        select r.*, u.email, u.first_name, u.last_name, u.deleted_at
        from password_reset_requests r
        left join users u on u.id=r.user_id
        where r.id=?
        limit 1
        """,
        (reset_id,),
    )


def _claim_delivery(gateway, reset_id, now_epoch):
    claim_token = secrets.token_urlsafe(24)
    mutation = gateway.execute(
        """
        update password_reset_requests
        set delivery_status='sending',
            delivery_attempts=delivery_attempts + 1,
            delivery_claim_token=?,
            delivery_claim_expires_at=?,
            delivery_last_error=null,
            delivery_updated_at=CURRENT_TIMESTAMP
        where id=? and sent_at is null and used_at is null
          and unixepoch(expires_at)>?
          and (
            delivery_status in ('queued','retry')
            or (
              delivery_status='sending'
              and coalesce(delivery_claim_expires_at, 0)<=?
            )
          )
        """,
        (
            claim_token,
            now_epoch + DELIVERY_LEASE_SECONDS,
            reset_id,
            now_epoch,
            now_epoch,
        ),
    )
    return claim_token if mutation.changes == 1 else None


def _preclaim_terminal_category(row, now_epoch):
    status = row.get("delivery_status")
    if status in TERMINAL_DELIVERY_STATUSES:
        return str(row.get("delivery_last_error") or status)
    if row.get("used_at"):
        return "reset_used"
    expires_at = row.get("expires_at")
    if not expires_at or _timestamp_epoch(expires_at) <= now_epoch:
        return "reset_expired"
    if row.get("deleted_at") or not row.get("email"):
        return "recipient_unavailable"
    return None


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
        raise EmailDeliveryTerminalError("side_effect_environment_invalid")
    if not side_effects_enabled:
        raise EmailDeliveryTerminalError("side_effects_disabled")
    if (
        parsed_origin.scheme != "https"
        or not parsed_origin.hostname
        or parsed_origin.hostname.lower() != expected_hostname
    ):
        raise EmailDeliveryTerminalError("app_origin_invalid")
    api_token = current_app.config.get("MAILERSEND_API_TOKEN")
    from_email = current_app.config.get("MAILERSEND_FROM_EMAIL")
    if not api_token or not from_email:
        raise EmailDeliveryTerminalError("provider_configuration_missing")
    return {
        "origin": origin,
        "api_token": api_token,
        "from_email": from_email,
        "from_name": current_app.config.get("MAILERSEND_FROM_NAME") or "Ordinarium",
    }


def _validate_recipient(row):
    recipient = str(row.get("email") or "").strip()
    parsed_name, parsed_address = parseaddr(recipient)
    if parsed_name or parsed_address != recipient or "@" not in parsed_address:
        raise EmailDeliveryTerminalError("recipient_invalid")


def _mailersend_payload(row, token, origin):
    name = (row.get("first_name") or "there").strip()
    reset_url = f"{origin}/reset-password/{token}"
    return {
        "from": {
            "email": current_app.config["MAILERSEND_FROM_EMAIL"],
            "name": current_app.config.get("MAILERSEND_FROM_NAME") or "Ordinarium",
        },
        "to": [{"email": row["email"], "name": name}],
        "subject": "Reset your Ordinarium password",
        "text": (
            f"Hello {name},\n\n"
            f"Reset your Ordinarium password:\n{reset_url}\n\n"
            "If you did not request this, you can ignore this email."
        ),
    }


def _send_mailersend(delivery_config, payload):
    transport = current_app.config.get("MAILERSEND_TRANSPORT")
    if transport:
        return transport(
            MAILERSEND_URL,
            headers={
                "Authorization": f"Bearer {delivery_config['api_token']}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
    return requests.post(
        MAILERSEND_URL,
        headers={
            "Authorization": f"Bearer {delivery_config['api_token']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )


def _persist_retry(gateway, reset_id, claim_token, category, retry_after):
    mutation = gateway.execute(
        """
        update password_reset_requests
        set delivery_status='retry',
            delivery_last_error=?,
            delivery_claim_token=null,
            delivery_claim_expires_at=null,
            delivery_updated_at=CURRENT_TIMESTAMP
        where id=? and delivery_status='sending' and delivery_claim_token=?
        """,
        (category, reset_id, claim_token),
    )
    if mutation.changes != 1:
        return _retry_response("retry_persistence_uncertain", retry_after)
    return _retry_response(category, retry_after)


def _fail_claimed_delivery(gateway, reset_id, claim_token, category):
    mutation = gateway.execute(
        """
        update password_reset_requests
        set delivery_status='failed',
            delivery_last_error=?,
            delivery_failed_at=CURRENT_TIMESTAMP,
            delivery_token_envelope=null,
            delivery_claim_token=null,
            delivery_claim_expires_at=null,
            delivery_updated_at=CURRENT_TIMESTAMP
        where id=? and delivery_status='sending' and delivery_claim_token=?
        """,
        (category, reset_id, claim_token),
    )
    return mutation.changes == 1


def _terminalize(gateway, reset_id, category):
    gateway.execute(
        """
        update password_reset_requests
        set delivery_status='failed',
            delivery_last_error=?,
            delivery_failed_at=CURRENT_TIMESTAMP,
            delivery_token_envelope=null,
            delivery_claim_token=null,
            delivery_claim_expires_at=null,
            delivery_updated_at=CURRENT_TIMESTAMP
        where id=? and delivery_status not in ('sent','accepted','suppressed','failed')
        """,
        (category, reset_id),
    )


def _retry_after(response, attempt):
    value = response.headers.get("retry-after") or response.headers.get("Retry-After")
    if value:
        try:
            return max(1, min(int(float(value)), MAX_RETRY_DELAY_SECONDS))
        except (TypeError, ValueError):
            try:
                parsed = parsedate_to_datetime(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                delay = int((parsed - datetime.now(timezone.utc)).total_seconds())
                return max(1, min(delay, MAX_RETRY_DELAY_SECONDS))
            except (TypeError, ValueError, OverflowError):
                pass
    return min(30 * (2 ** max(0, attempt - 1)), 900)


def _backoff(row):
    return min(30 * (2 ** max(0, int(row["delivery_attempts"]) - 1)), 900)


def _timestamp_epoch(value):
    if isinstance(value, (int, float)):
        return int(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _config_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _terminal_response(category, **values):
    return {
        "persisted": True,
        "disposition": "terminal",
        "category": category,
        **values,
    }, 200


def _retry_response(category, retry_after_seconds):
    return {
        "persisted": True,
        "disposition": "retry",
        "category": category,
        "retry_after_seconds": int(retry_after_seconds),
    }, 503
