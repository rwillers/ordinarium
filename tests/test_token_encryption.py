import base64

import pytest

from ordinarium.token_encryption import (
    TokenEncryptionError,
    decrypt_token,
    encrypt_token,
    token_is_encrypted,
)


def test_aes_gcm_token_envelope_round_trip_uses_random_nonce(app):
    with app.app_context():
        first = encrypt_token("secret-token", user_id=42, field_name="access_token")
        second = encrypt_token("secret-token", user_id=42, field_name="access_token")

        assert first.startswith("aesgcm:v1:")
        assert token_is_encrypted(first)
        assert first != second
        assert (
            decrypt_token(first, user_id=42, field_name="access_token")
            == "secret-token"
        )


def test_token_envelope_authenticates_user_and_field(app):
    with app.app_context():
        envelope = encrypt_token("secret-token", user_id=42, field_name="access_token")

        with pytest.raises(TokenEncryptionError):
            decrypt_token(envelope, user_id=43, field_name="access_token")
        with pytest.raises(TokenEncryptionError):
            decrypt_token(envelope, user_id=42, field_name="refresh_token")


def test_token_envelope_rejects_tampering(app):
    with app.app_context():
        envelope = encrypt_token("secret-token", user_id=42, field_name="access_token")
        prefix, version, nonce, ciphertext_value = envelope.split(":")
        padding = "=" * (-len(ciphertext_value) % 4)
        ciphertext = bytearray(base64.urlsafe_b64decode(ciphertext_value + padding))
        ciphertext[-1] ^= 1
        tampered_ciphertext = (
            base64.urlsafe_b64encode(ciphertext).rstrip(b"=").decode("ascii")
        )
        tampered_envelope = ":".join((prefix, version, nonce, tampered_ciphertext))

        with pytest.raises(TokenEncryptionError):
            decrypt_token(
                tampered_envelope,
                user_id=42,
                field_name="access_token",
            )


def test_legacy_plaintext_token_is_read_without_modification(app):
    with app.app_context():
        assert (
            decrypt_token("legacy-plaintext", user_id=42, field_name="access_token")
            == "legacy-plaintext"
        )
