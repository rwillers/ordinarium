from dataclasses import dataclass

from flask import g
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required as flask_login_required,
)

from .user_store import get_user_by_id

login_manager = LoginManager()


@dataclass
class OrdinariumUser(UserMixin):
    id: int
    first_name: str
    last_name: str
    email: str
    password_hash: str | None = None

    @classmethod
    def from_row(cls, row):
        if not row:
            return None
        return cls(
            id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            email=row["email"],
            password_hash=row["password_hash"],
        )

    def __getitem__(self, key):
        return getattr(self, key)


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
