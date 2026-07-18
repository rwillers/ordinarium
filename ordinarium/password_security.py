from dataclasses import dataclass

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from werkzeug.security import check_password_hash


# Pin the encoded Argon2id parameters so library-default changes do not silently
# alter Ordinarium's password policy. These meet OWASP's 19 MiB baseline.
PASSWORD_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19 * 1024,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


@dataclass(frozen=True)
class PasswordVerification:
    valid: bool
    replacement_hash: str | None = None


def hash_password(password):
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash, password):
    if not password_hash:
        return PasswordVerification(False)

    if password_hash.startswith("$argon2"):
        try:
            PASSWORD_HASHER.verify(password_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return PasswordVerification(False)
        replacement_hash = None
        if PASSWORD_HASHER.check_needs_rehash(password_hash):
            replacement_hash = hash_password(password)
        return PasswordVerification(True, replacement_hash)

    try:
        valid = check_password_hash(password_hash, password)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        return PasswordVerification(False)
    return PasswordVerification(True, hash_password(password))
