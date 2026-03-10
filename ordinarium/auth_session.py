from dataclasses import dataclass
from datetime import datetime, timedelta

from flask import g, request
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required as flask_login_required,
)

from .db import get_db
from .feature_flags import parse_feature_flags
from .user_store import get_user_by_id
from .user_settings import resolve_user_settings

login_manager = LoginManager()
ACCESS_UPDATE_WINDOW = timedelta(hours=1)


@dataclass
class OrdinariumUser(UserMixin):
    id: int
    first_name: str
    last_name: str
    email: str
    password_hash: str | None = None
    default_rite: str | None = None
    default_bible_translation: str | None = None
    default_service_time: str | None = None
    greeting_response_form: str | None = None
    feature_flags: dict | None = None
    last_accessed_at: str | None = None

    @classmethod
    def from_row(cls, row):
        if not row:
            return None
        feature_value = None
        if hasattr(row, "keys") and "feature_flags" in row.keys():
            feature_value = row["feature_flags"]
        settings = resolve_user_settings(row)
        return cls(
            id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            email=row["email"],
            password_hash=row["password_hash"],
            default_rite=settings["default_rite"],
            default_bible_translation=settings["default_bible_translation"],
            default_service_time=settings["default_service_time"],
            greeting_response_form=_row_value(row, "greeting_response_form"),
            feature_flags=parse_feature_flags(feature_value),
            last_accessed_at=_row_value(row, "last_accessed_at"),
        )

    def __getitem__(self, key):
        return getattr(self, key)

    def has_feature(self, feature):
        if not self.feature_flags:
            return False
        return bool(self.feature_flags.get(feature))


def init_login(app):
    login_manager.init_app(app)
    login_manager.login_view = "main.login"

    @login_manager.user_loader
    def load_user(user_id):
        if not user_id:
            return None
        try:
            user_id = int(user_id)
        except ValueError:
            return None
        row = get_user_by_id(user_id)
        return OrdinariumUser.from_row(row)


def build_user(row):
    return OrdinariumUser.from_row(row)


def register_user_context(bp):
    @bp.before_app_request
    def load_logged_in_user():
        if current_user.is_authenticated:
            g.user = current_user._get_current_object()
            _update_last_accessed_at(g.user)
        else:
            g.user = None

    @bp.app_context_processor
    def inject_user():
        return {"user": g.user}


login_required = flask_login_required


def _row_value(row, key):
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    return None


def _parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _update_last_accessed_at(user):
    if request.endpoint == "static":
        return

    now = datetime.utcnow()
    last_accessed_at = _parse_timestamp(user.last_accessed_at)
    if last_accessed_at and now - last_accessed_at < ACCESS_UPDATE_WINDOW:
        return

    now_value = now.isoformat()
    db = get_db()
    db.execute(
        "update users set last_accessed_at=? where id=?",
        (now_value, user["id"]),
    )
    db.commit()
    user.last_accessed_at = now_value
