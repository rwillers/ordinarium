from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from flask import current_app

from .db import get_db


def get_user_by_id(user_id):
    if not user_id:
        return None
    db = get_db()
    user = db.execute(
        """
        select id, first_name, last_name, email, password_hash,
               feature_flags, created_at, last_login_at
        from users
        where id=? and deleted_at is null
        limit 1
        """,
        (user_id,),
    ).fetchone()
    return user


def get_user_by_email(email):
    if not email:
        return None
    db = get_db()
    user = db.execute(
        """
        select id, first_name, last_name, email, password_hash,
               feature_flags, created_at, last_login_at
        from users
        where email=? and deleted_at is null
        limit 1
        """,
        (email,),
    ).fetchone()
    return user


def create_password_reset_token(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return None
    serializer = _password_reset_serializer()
    payload = {"user_id": user["id"], "pw": user["password_hash"] or ""}
    return serializer.dumps(payload)


def get_password_reset_record(token):
    if not token:
        return None
    serializer = _password_reset_serializer()
    max_age = int(current_app.config.get("PASSWORD_RESET_EXPIRY_MINUTES", 60)) * 60
    try:
        payload = serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    user_id = payload.get("user_id")
    password_hash = payload.get("pw") or ""
    user = get_user_by_id(user_id)
    if not user:
        return None
    if (user["password_hash"] or "") != password_hash:
        return None
    return {"user_id": user["id"]}


def _password_reset_serializer():
    secret_value = current_app.config.get("SECRET_KEY")
    if not secret_value:
        raise RuntimeError("SECRET_KEY must be set before generating reset tokens.")
    salt = current_app.config.get("PASSWORD_RESET_SALT", "password-reset")
    return URLSafeTimedSerializer(secret_value, salt=salt)
