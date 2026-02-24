import sqlite3

import pytest

from ordinarium.db import get_db


def test_services_reject_invalid_json(app, user_factory):
    user_id = user_factory(email="json-check@example.com")
    with app.app_context():
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                insert into services (
                  user_id,
                  title,
                  rite,
                  text_order,
                  text_disabled,
                  lesson_overrides
                ) values (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    "Bad JSON",
                    "Renewed Ancient Text",
                    "[",
                    "[]",
                    "{}",
                ),
            )


def test_texts_reject_invalid_subcycles_json(app):
    with app.app_context():
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                insert into texts (
                  type,
                  filter_type,
                  filter_content,
                  text,
                  title,
                  default_order,
                  subcycles
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "lesson",
                    "proper",
                    "AdventI",
                    "Text",
                    "Title",
                    1,
                    "[",
                ),
            )


def test_services_reject_invalid_proper_overrides_json(app, user_factory):
    user_id = user_factory(email="proper-json-check@example.com")
    with app.app_context():
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                insert into services (
                  user_id,
                  title,
                  rite,
                  text_order,
                  text_disabled,
                  lesson_overrides,
                  proper_overrides
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    "Bad Proper JSON",
                    "Renewed Ancient Text",
                    "[]",
                    "[]",
                    "{}",
                    "[",
                ),
            )


def test_services_reject_invalid_service_option_values_json(app, user_factory):
    user_id = user_factory(email="service-options-json-check@example.com")
    with app.app_context():
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                insert into services (
                  user_id,
                  title,
                  rite,
                  text_order,
                  text_disabled,
                  lesson_overrides,
                  proper_overrides,
                  service_option_values
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    "Bad Service Option JSON",
                    "Renewed Ancient Text",
                    "[]",
                    "[]",
                    "{}",
                    "{}",
                    "[",
                ),
            )
