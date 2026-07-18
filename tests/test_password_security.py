from werkzeug.security import generate_password_hash

from ordinarium.password_security import hash_password, verify_password


def test_hash_password_uses_pinned_argon2id_parameters():
    password_hash = hash_password("strong-pass")

    assert password_hash.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert verify_password(password_hash, "strong-pass").valid


def test_verify_password_rejects_wrong_or_malformed_hashes():
    assert not verify_password(hash_password("strong-pass"), "wrong-pass").valid
    assert not verify_password("not-a-password-hash", "strong-pass").valid


def test_verify_password_upgrades_legacy_werkzeug_hash():
    legacy_hash = generate_password_hash("strong-pass", method="scrypt")

    result = verify_password(legacy_hash, "strong-pass")

    assert result.valid
    assert result.replacement_hash.startswith("$argon2id$")
    assert verify_password(result.replacement_hash, "strong-pass").valid
