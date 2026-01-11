import json
import sys
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ordinarium import create_app
from ordinarium.db import get_db, init_db


@pytest.fixture()
def app(tmp_path):
    app = create_app()
    app.config.update(
        TESTING=True,
        DATABASE=str(tmp_path / "test.db"),
        SECRET_KEY="test",
    )
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
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "password_hash": generate_password_hash(password),
        }
        with app.app_context():
            db = get_db()
            db.execute("insert into users (data) values (?)", (json.dumps(payload),))
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
        payload = {
            "user_id": user_id,
            "title": title,
            "rite": rite,
            "season": season,
            "service_date": service_date,
            "text_order": text_order,
            "text_disabled": text_disabled,
            "observance_handle": observance_handle,
        }
        with app.app_context():
            db = get_db()
            db.execute(
                "insert into services (id, data) values (?, ?)",
                (service_id, json.dumps(payload)),
            )
            db.commit()
        return service_id

    return _factory


@pytest.fixture()
def auth_client(client, user_factory):
    user_id = user_factory()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client, user_id
