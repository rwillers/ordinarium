from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from flask import current_app

from .db import get_database_gateway


USER_COLUMNS = """
    id, first_name, last_name, email, password_hash,
    default_rite, default_bible_translation, default_service_time,
    greeting_response_form,
    feature_flags, created_at, last_login_at, last_accessed_at
"""


def get_user_by_id(user_id):
    if not user_id:
        return None
    gateway = get_database_gateway()
    return gateway.fetch_one(
        f"""
        select {USER_COLUMNS}
        from users
        where id=? and deleted_at is null
        limit 1
        """,
        (user_id,),
    )


def get_user_by_email(email):
    if not email:
        return None
    gateway = get_database_gateway()
    return gateway.fetch_one(
        f"""
        select {USER_COLUMNS}
        from users
        where email=? and deleted_at is null
        limit 1
        """,
        (email,),
    )


def create_user(first_name, last_name, email, password_hash, timestamp):
    gateway = get_database_gateway()
    user_id = gateway.allocate_id("users")
    gateway.execute(
        """
        insert into users (
            id,
            first_name,
            last_name,
            email,
            password_hash,
            created_at,
            last_login_at
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            first_name,
            last_name,
            email,
            password_hash,
            timestamp,
            timestamp,
        ),
    )
    return get_user_by_id(user_id)


def record_user_login(user_id, timestamp):
    get_database_gateway().execute(
        "update users set last_login_at=? where id=?",
        (timestamp, user_id),
    )


def record_user_access(user_id, timestamp):
    get_database_gateway().execute(
        "update users set last_accessed_at=? where id=?",
        (timestamp, user_id),
    )


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
