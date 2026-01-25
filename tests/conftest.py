import json
import sys
from pathlib import Path

import pytest
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ordinarium import create_app
from ordinarium.db import get_db, init_db


class CSRFClient(FlaskClient):
    def _ensure_csrf_token(self):
        token = None
        with self.session_transaction() as session:
            token = session.get("_csrf_token")
            if not token:
                token = "test-csrf-token"
                session["_csrf_token"] = token
        return token

    def open(self, *args, **kwargs):
        method = kwargs.get("method", "GET")
        if method and method.upper() == "POST":
            token = self._ensure_csrf_token()
            headers = kwargs.pop("headers", {}) or {}
            headers = dict(headers)
            headers.setdefault("X-CSRF-Token", token)
            kwargs["headers"] = headers
        return super().open(*args, **kwargs)


@pytest.fixture()
def app(tmp_path):
    app = create_app()
    app.config.update(
        TESTING=True,
        DATABASE=str(tmp_path / "test.db"),
        SECRET_KEY="test",
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
    )
    app.test_client_class = CSRFClient
    with app.app_context():
        init_db()
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user_factory(app):
    def _factory(
        email="user@example.com",
        password="password123",
        first_name="Test",
        last_name="User",
    ):
        with app.app_context():
            db = get_db()
            db.execute(
                "insert into users (first_name, last_name, email, password_hash) values (?, ?, ?, ?)",
                (first_name, last_name, email, generate_password_hash(password)),
            )
            db.commit()
            user = db.execute(
                "select id from users where email=? limit 1", (email,)
            ).fetchone()
            return user["id"]

    return _factory


@pytest.fixture()
def service_factory(app):
    def _factory(
        user_id,
        service_id=1,
        title=None,
        rite="Renewed Ancient Text",
        season=None,
        service_date=None,
        text_order=None,
        text_disabled=None,
        observance_handle=None,
    ):
        with app.app_context():
            db = get_db()
            db.execute(
                """
                insert into services (
                  id,
                  user_id,
                  title,
                  rite,
                  season,
                  service_date,
                  text_order,
                  text_disabled,
                  observance_handle,
                  lesson_overrides,
                  offertory_sentence_id
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    service_id,
                    user_id,
                    title,
                    rite,
                    season,
                    service_date,
                    text_order,
                    text_disabled,
                    observance_handle,
                    json.dumps({}),
                    None,
                ),
            )
            db.commit()
        return service_id

    return _factory


@pytest.fixture()
def auth_client(client, user_factory):
    user_id = user_factory()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True
    return client, user_id
