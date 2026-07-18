import base64
import binascii
import json
import os
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app


ENVELOPE_PREFIX = "aesgcm"
NONCE_BYTES = 12
_VERSION_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


class TokenEncryptionError(RuntimeError):
    pass


def encrypt_token(value, *, user_id, field_name):
    if value is None:
        return None
    version, key = _primary_key()
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(
        nonce,
        str(value).encode("utf-8"),
        _associated_data(user_id, field_name),
    )
    return ":".join(
        (
            ENVELOPE_PREFIX,
            version,
            _encode(nonce),
            _encode(ciphertext),
        )
    )


def decrypt_token(value, *, user_id, field_name):
    if value is None or not str(value).startswith(f"{ENVELOPE_PREFIX}:"):
        return value
    parts = str(value).split(":")
    if len(parts) != 4:
        raise TokenEncryptionError("PCO token envelope is malformed.")
    _prefix, version, nonce_value, ciphertext_value = parts
    keys = _configured_keys()
    key = keys.get(version)
    if key is None:
        raise TokenEncryptionError("PCO token envelope uses an unknown key version.")
    try:
        nonce = _decode(nonce_value)
        ciphertext = _decode(ciphertext_value)
        if len(nonce) != NONCE_BYTES:
            raise ValueError
        plaintext = AESGCM(key).decrypt(
            nonce,
            ciphertext,
            _associated_data(user_id, field_name),
        )
        return plaintext.decode("utf-8")
    except (InvalidTag, UnicodeDecodeError, ValueError, binascii.Error) as exc:
        raise TokenEncryptionError(
            "PCO token envelope could not be decrypted."
        ) from exc


def token_is_encrypted(value):
    return bool(value and str(value).startswith(f"{ENVELOPE_PREFIX}:"))


def _primary_key():
    keys = _configured_keys()
    version = current_app.config.get("PCO_TOKEN_ENCRYPTION_PRIMARY_VERSION", "v1")
    if version not in keys:
        raise TokenEncryptionError(
            "PCO_TOKEN_ENCRYPTION_PRIMARY_VERSION does not identify a configured key."
        )
    return version, keys[version]


def _configured_keys():
    raw_keys = current_app.config.get("PCO_TOKEN_ENCRYPTION_KEYS")
    if isinstance(raw_keys, str):
        try:
            raw_keys = json.loads(raw_keys)
        except json.JSONDecodeError as exc:
            raise TokenEncryptionError(
                "PCO_TOKEN_ENCRYPTION_KEYS must be a JSON object."
            ) from exc
    if not raw_keys:
        legacy_key = current_app.config.get("PCO_TOKEN_ENCRYPTION_KEY")
        raw_keys = {"v1": legacy_key} if legacy_key else {}
    if not isinstance(raw_keys, dict) or not raw_keys:
        raise TokenEncryptionError("PCO token encryption keys are not configured.")

    keys = {}
    for version, encoded_key in raw_keys.items():
        if not isinstance(version, str) or not _VERSION_PATTERN.fullmatch(version):
            raise TokenEncryptionError("PCO token key version is invalid.")
        if not isinstance(encoded_key, str):
            raise TokenEncryptionError("PCO token encryption key is invalid.")
        try:
            key = _decode(encoded_key)
        except (ValueError, binascii.Error) as exc:
            raise TokenEncryptionError("PCO token encryption key is invalid.") from exc
        if len(key) not in {16, 24, 32}:
            raise TokenEncryptionError(
                "PCO token encryption key has an invalid length."
            )
        keys[version] = key
    return keys


def _associated_data(user_id, field_name):
    return f"ordinarium:pco-token:{user_id}:{field_name}".encode("utf-8")


def _encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value):
    if not isinstance(value, str):
        raise ValueError
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)
