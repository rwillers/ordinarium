from dataclasses import dataclass

from flask import g
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required as flask_login_required,
)

from .feature_flags import parse_feature_flags
from .user_store import get_user_by_id

login_manager = LoginManager()


@dataclass
class OrdinariumUser(UserMixin):
    id: int
    first_name: str
    last_name: str
    email: str
    password_hash: str | None = None
    feature_flags: dict | None = None

    @classmethod
    def from_row(cls, row):
        if not row:
            return None
        feature_value = None
        if hasattr(row, "keys") and "feature_flags" in row.keys():
            feature_value = row["feature_flags"]
        return cls(
            id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            email=row["email"],
            password_hash=row["password_hash"],
            feature_flags=parse_feature_flags(feature_value),
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
        else:
            g.user = None

    @bp.app_context_processor
    def inject_user():
        return {"user": g.user}


login_required = flask_login_required
