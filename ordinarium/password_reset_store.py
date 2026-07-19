from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app

from .db import get_database_gateway
from .infrastructure import DatabaseStatement


TOKEN_VERSION = "pr1"
ENVELOPE_VERSION = "v1"
DELIVERY_AAD_PREFIX = "ordinarium:password-reset-delivery"
SIGNING_CONTEXT = "ordinarium:password-reset-token:v1"


class PasswordResetConfigurationError(RuntimeError):
    pass


class PasswordResetEnvelopeError(ValueError):
    pass


def create_queued_password_reset(user_id, *, now=None):
    """Persist a reset secret hash and an encrypted copy used only for delivery."""
    now = _utc_now(now)
    reset_id = secrets.token_urlsafe(18)
    secret = secrets.token_urlsafe(32)
    signature = _token_signature(reset_id, secret)
    token = ".".join((TOKEN_VERSION, reset_id, secret, signature))
    token_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    expiry_minutes = int(current_app.config["PASSWORD_RESET_EXPIRY_MINUTES"])
    expires_at = _database_timestamp(now + timedelta(minutes=expiry_minutes))
    envelope = encrypt_delivery_token(reset_id, token)

    get_database_gateway().execute(
        """
        insert into password_reset_requests (
          id, user_id, token_hash, expires_at, delivery_token_envelope
        ) values (?, ?, ?, ?, ?)
        """,
        (reset_id, user_id, token_hash, expires_at, envelope),
    )
    return {"reset_id": reset_id, "token": token, "expires_at": expires_at}


def get_queued_password_reset_record(token, *, now=None):
    parsed = _parse_token(token)
    if parsed is None:
        return None
    reset_id, token_hash = parsed
    now_epoch = int(_utc_now(now).timestamp())
    row = get_database_gateway().fetch_one(
        """
        select r.id, r.user_id
        from password_reset_requests r
        join users u on u.id=r.user_id and u.deleted_at is null
        where r.id=? and r.token_hash=? and r.used_at is null
          and unixepoch(r.expires_at)>?
        limit 1
        """,
        (reset_id, token_hash, now_epoch),
    )
    if row is None:
        return None
    return {"user_id": row["user_id"], "queued_reset_id": row["id"]}


def consume_queued_password_reset(token, password_hash, *, now=None):
    """Atomically consume a persisted reset and replace the user's password."""
    parsed = _parse_token(token)
    if parsed is None:
        return False
    reset_id, token_hash = parsed
    now_epoch = int(_utc_now(now).timestamp())
    claim_token = secrets.token_urlsafe(24)
    gateway = get_database_gateway()
    results = gateway.batch(
        [
            DatabaseStatement(
                """
                update password_reset_requests
                set used_at=CURRENT_TIMESTAMP,
                    claim_token=?,
                    delivery_token_envelope=null,
                    delivery_status=case
                      when delivery_status in ('sent','accepted') then delivery_status
                      else 'suppressed'
                    end,
                    delivery_last_error=case
                      when delivery_status in ('sent','accepted') then delivery_last_error
                      else 'reset_used'
                    end,
                    delivery_claim_token=null,
                    delivery_claim_expires_at=null,
                    delivery_updated_at=CURRENT_TIMESTAMP
                where id=? and token_hash=? and used_at is null
                  and unixepoch(expires_at)>?
                  and exists (
                    select 1 from users
                    where users.id=password_reset_requests.user_id
                      and users.deleted_at is null
                  )
                """,
                (claim_token, reset_id, token_hash, now_epoch),
            ),
            DatabaseStatement(
                """
                update users
                set password_hash=?
                where id=(
                  select user_id from password_reset_requests
                  where id=? and claim_token=? and used_at is not null
                ) and deleted_at is null
                """,
                (password_hash, reset_id, claim_token),
            ),
        ]
    )
    return bool(
        len(results) == 2
        and results[0].metadata.changes == 1
        and results[1].metadata.changes == 1
    )


def encrypt_delivery_token(reset_id, token):
    key = _delivery_key()
    nonce = os.urandom(12)
    plaintext = json.dumps(
        {"reset_id": reset_id, "token": token}, separators=(",", ":")
    ).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, _delivery_aad(reset_id))
    return ":".join(
        (
            "reset-delivery",
            ENVELOPE_VERSION,
            _base64url_encode(nonce),
            _base64url_encode(ciphertext),
        )
    )


def decrypt_delivery_token(reset_id, envelope):
    try:
        prefix, version, encoded_nonce, encoded_ciphertext = envelope.split(":")
        if prefix != "reset-delivery" or version != ENVELOPE_VERSION:
            raise PasswordResetEnvelopeError("Unsupported reset delivery envelope.")
        nonce = _base64url_decode(encoded_nonce)
        ciphertext = _base64url_decode(encoded_ciphertext)
        plaintext = AESGCM(_delivery_key()).decrypt(
            nonce, ciphertext, _delivery_aad(reset_id)
        )
        payload = json.loads(plaintext.decode("utf-8"))
        if payload.get("reset_id") != reset_id or not isinstance(
            payload.get("token"), str
        ):
            raise PasswordResetEnvelopeError("Reset delivery envelope mismatch.")
        return payload["token"]
    except PasswordResetConfigurationError:
        raise
    except (AttributeError, TypeError, ValueError, binascii.Error, InvalidTag) as exc:
        raise PasswordResetEnvelopeError("Invalid reset delivery envelope.") from exc


def is_queued_password_reset_token(token):
    return isinstance(token, str) and token.startswith(f"{TOKEN_VERSION}.")


def _parse_token(token):
    if not isinstance(token, str):
        return None
    try:
        version, reset_id, secret, signature = token.split(".")
    except ValueError:
        return None
    if version != TOKEN_VERSION or not reset_id or not secret or not signature:
        return None
    expected = _token_signature(reset_id, secret)
    if not hmac.compare_digest(signature, expected):
        return None
    return reset_id, hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _token_signature(reset_id, secret):
    configured = current_app.config.get("SECRET_KEY")
    if not configured:
        raise PasswordResetConfigurationError(
            "SECRET_KEY must be set before generating reset tokens."
        )
    key = configured if isinstance(configured, bytes) else str(configured).encode()
    message = f"{SIGNING_CONTEXT}:{reset_id}:{secret}".encode("utf-8")
    return _base64url_encode(hmac.new(key, message, hashlib.sha256).digest())


def _delivery_key():
    configured = current_app.config.get("PASSWORD_RESET_DELIVERY_KEY")
    if not configured:
        raise PasswordResetConfigurationError(
            "PASSWORD_RESET_DELIVERY_KEY must be configured for queued resets."
        )
    if isinstance(configured, bytes):
        key = configured
    else:
        try:
            key = _base64url_decode(str(configured))
        except (ValueError, binascii.Error) as exc:
            raise PasswordResetConfigurationError(
                "PASSWORD_RESET_DELIVERY_KEY must be base64 encoded."
            ) from exc
    if len(key) != 32:
        raise PasswordResetConfigurationError(
            "PASSWORD_RESET_DELIVERY_KEY must decode to exactly 32 bytes."
        )
    return key


def _delivery_aad(reset_id):
    return f"{DELIVERY_AAD_PREFIX}:{ENVELOPE_VERSION}:{reset_id}".encode("utf-8")


def _base64url_encode(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Invalid base64 value.")
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)


def _utc_now(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _database_timestamp(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
