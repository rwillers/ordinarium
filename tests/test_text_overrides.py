import sqlite3
from pathlib import Path

import pytest

from ordinarium.db import get_database_gateway, get_db
from ordinarium.text_overrides import (
    CUSTOMIZABLE_TEXT_TYPES,
    TextOverrideValidationError,
    acknowledge_user_text_override,
    canonical_template_slots,
    canonical_text_for_house_use,
    canonical_text_hash,
    delete_user_text_override,
    load_customizable_texts,
    load_user_text_overrides,
    resolve_text_override,
    render_house_use_slots,
    upsert_user_text_override,
)


ROOT = Path(__file__).parents[1]


def test_upsert_load_and_resolve_preserve_canonical_identity(app):
    with app.app_context():
        canonical = _plain_text("ordinarium")
        replacement = "*Celebrant and People together say*\n\n{{ shown as text }}"

        upsert_user_text_override(1, canonical["id"], replacement)
        upsert_user_text_override(1, canonical["id"], replacement + " updated")

        overrides = load_user_text_overrides(1)
        override = overrides[canonical["id"]]
        resolved = resolve_text_override(canonical, overrides)

        assert override["replacement_text"] == replacement + " updated"
        assert override["base_text_hash"] == canonical_text_hash(canonical["text"])
        assert override["current_text_hash"] == override["base_text_hash"]
        assert override["is_stale"] is False
        assert resolved["id"] == canonical["id"]
        assert resolved["type"] == canonical["type"]
        assert resolved["title"] == canonical["title"]
        assert resolved["text"] == replacement + " updated"
        assert resolved["house_use_applied"] is True
        assert "{{ shown as text }}" in resolved["text"]
        count = (
            get_db()
            .execute(
                "select count(*) from user_text_overrides where user_id=? and text_id=?",
                (1, canonical["id"]),
            )
            .fetchone()[0]
        )
        assert count == 1


def test_stale_state_tracks_changes_to_official_text(app):
    with app.app_context():
        canonical = _plain_text("ordinarium")
        upsert_user_text_override(1, canonical["id"], "Local form")

        get_database_gateway().execute(
            "update texts set text=? where id=?",
            (canonical["text"] + "\n\nOfficial revision", canonical["id"]),
        )

        override = load_user_text_overrides(1)[canonical["id"]]
        assert override["is_stale"] is True
        assert override["current_text_hash"] != override["base_text_hash"]
        assert override["replacement_text"] == "Local form"


def test_acknowledge_rebases_existing_override_without_revalidating_text(app):
    with app.app_context():
        canonical = _plain_text("ordinarium")
        upsert_user_text_override(1, canonical["id"], "Local form")
        templated_revision = canonical["text"] + "\n\n{{ new_template_token }}"
        get_database_gateway().execute(
            "update texts set text=? where id=?",
            (templated_revision, canonical["id"]),
        )
        get_database_gateway().execute(
            """
            update user_text_overrides
            set updated_at='2000-01-01 00:00:00'
            where user_id=? and text_id=?
            """,
            (1, canonical["id"]),
        )
        current_hash = canonical_text_hash(templated_revision)

        acknowledge_user_text_override(1, canonical["id"], current_hash)

        override = load_user_text_overrides(1)[canonical["id"]]
        assert override["replacement_text"] == "Local form"
        assert override["base_text_hash"] == current_hash
        assert override["is_stale"] is False
        assert override["updated_at"] != "2000-01-01 00:00:00"


def test_account_scoping_and_delete_do_not_cross_accounts(app, user_factory):
    second_user_id = user_factory(email="second@example.com")
    with app.app_context():
        canonical = _plain_text("acclamation")
        upsert_user_text_override(1, canonical["id"], "First parish")
        upsert_user_text_override(second_user_id, canonical["id"], "Second parish")

        assert (
            load_user_text_overrides(1)[canonical["id"]]["replacement_text"]
            == "First parish"
        )
        assert (
            load_user_text_overrides(second_user_id)[canonical["id"]][
                "replacement_text"
            ]
            == "Second parish"
        )

        assert delete_user_text_override(1, canonical["id"]) is True
        assert delete_user_text_override(1, canonical["id"]) is False
        assert load_user_text_overrides(1) == {}
        assert canonical["id"] in load_user_text_overrides(second_user_id)


def test_allows_supporting_fragments_and_supported_templates(app):
    with app.app_context():
        acclamation = _plain_text("acclamation")
        upsert_user_text_override(1, acclamation["id"], "Blessed be God")

        templated = get_database_gateway().fetch_one(
            """
            select id, text from texts
            where type='ordinarium' and text like '%{{%'
            order by id limit 1
            """
        )
        replacement = canonical_text_for_house_use(templated["text"])
        upsert_user_text_override(1, templated["id"], replacement)

        lesson = get_database_gateway().fetch_one(
            "select id from texts where type='lesson' limit 1"
        )

        with pytest.raises(TextOverrideValidationError) as type_error:
            upsert_user_text_override(1, lesson["id"], "Local text")
        assert type_error.value.code == "text_type_not_customizable"

        assert (
            load_user_text_overrides(1)[templated["id"]]["replacement_text"]
            == replacement
        )


def test_rejects_unsupported_templates_and_invalid_dynamic_slots(app):
    with app.app_context():
        gateway = get_database_gateway()
        templated = gateway.fetch_one(
            """
            select id, text from texts
            where type='ordinarium' and text like '%{{%'
            order by id limit 1
            """
        )
        replacement = canonical_text_for_house_use(templated["text"])
        slot_token = replacement[replacement.index("[[") : replacement.index("]]") + 2]

        with pytest.raises(TextOverrideValidationError) as missing_error:
            upsert_user_text_override(
                1, templated["id"], replacement.replace(slot_token, "")
            )
        assert missing_error.value.code == "house_use_slots_invalid"

        with pytest.raises(TextOverrideValidationError) as duplicate_error:
            upsert_user_text_override(
                1, templated["id"], f"{replacement}\n\n{slot_token}"
            )
        assert duplicate_error.value.code == "house_use_slots_invalid"

        with pytest.raises(TextOverrideValidationError) as unknown_error:
            upsert_user_text_override(
                1, templated["id"], f"{replacement}\n\n[[Unknown value]]"
            )
        assert unknown_error.value.code == "house_use_slot_unknown"

        gateway.execute(
            "update texts set text=? where id=?",
            ("{% if dangerous %}Local{% endif %}", templated["id"]),
        )
        with pytest.raises(TextOverrideValidationError) as template_error:
            upsert_user_text_override(1, templated["id"], "Local text")
        assert template_error.value.code == "templated_text_not_customizable"


def test_dynamic_slot_rendering_does_not_evaluate_user_jinja():
    replacement = "Before [[Acclamation text]] after {{ 7 * 7 }}"

    rendered = render_house_use_slots(
        replacement,
        {"acclamation": "*Celebrant* Blessed be God."},
    )

    assert rendered == "Before *Celebrant* Blessed be God. after {{ 7 * 7 }}"


def test_customizable_text_listing_uses_allowlist_and_safe_templates(app):
    with app.app_context():
        rows = load_customizable_texts()

    assert rows
    assert {row["type"] for row in rows} <= CUSTOMIZABLE_TEXT_TYPES
    assert {"ordinarium", "acclamation"} <= {row["type"] for row in rows}
    assert any("{{" in (row["text"] or "") for row in rows)
    assert all(canonical_template_slots(row["text"]) is not None for row in rows)


def test_batched_load_uses_one_query_and_computes_staleness(monkeypatch):
    class RecordingGateway:
        def __init__(self):
            self.fetch_all_calls = 0

        def fetch_all(self, sql, params=()):
            self.fetch_all_calls += 1
            assert "where overrides.user_id=?" in sql
            assert params == (7,)
            return [
                {
                    "user_id": 7,
                    "text_id": 42,
                    "replacement_text": "Local",
                    "base_text_hash": canonical_text_hash("Old"),
                    "created_at": "2026-01-01",
                    "updated_at": "2026-01-01",
                    "canonical_type": "ordinarium",
                    "canonical_text": "New",
                    "canonical_title": "Prayer",
                    "canonical_detailed_title": None,
                    "canonical_filter_type": "rite",
                    "canonical_filter_content": "Rite",
                    "canonical_default_order": 10,
                }
            ]

    gateway = RecordingGateway()
    monkeypatch.setattr(
        "ordinarium.text_overrides.get_database_gateway", lambda: gateway
    )

    overrides = load_user_text_overrides(7)

    assert gateway.fetch_all_calls == 1
    assert overrides[42]["is_stale"] is True


@pytest.mark.parametrize(
    "migration_path",
    [
        ROOT / "scripts/migrations/043_add_user_text_overrides.sql",
        ROOT / "migrations/d1/0006_user_text_overrides.sql",
    ],
)
def test_forward_migrations_create_constraints_and_index(migration_path):
    connection = sqlite3.connect(":memory:")
    connection.execute("pragma foreign_keys=on")
    connection.execute("create table users (id integer primary key)")
    connection.execute("create table texts (id integer primary key)")
    connection.executescript(migration_path.read_text(encoding="utf-8"))
    connection.execute("insert into users (id) values (1)")
    connection.execute("insert into texts (id) values (2)")

    connection.execute(
        """
        insert into user_text_overrides (
          user_id, text_id, replacement_text, base_text_hash
        ) values (1, 2, 'Local', 'hash')
        """
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            insert into user_text_overrides (
              user_id, text_id, replacement_text, base_text_hash
            ) values (1, 2, 'Duplicate', 'hash')
            """
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            insert into user_text_overrides (
              user_id, text_id, replacement_text, base_text_hash
            ) values (999, 2, 'Missing user', 'hash')
            """
        )

    indexes = {
        row[1] for row in connection.execute("pragma index_list(user_text_overrides)")
    }
    assert "idx_user_text_overrides_text_id" in indexes

    connection.execute("delete from users where id=1")
    assert (
        connection.execute("select count(*) from user_text_overrides").fetchone()[0]
        == 0
    )

    connection.execute("insert into users (id) values (1)")
    connection.execute(
        """
        insert into user_text_overrides (
          user_id, text_id, replacement_text, base_text_hash
        ) values (1, 2, 'Local again', 'hash')
        """
    )
    connection.execute("delete from texts where id=2")
    assert (
        connection.execute("select count(*) from user_text_overrides").fetchone()[0]
        == 0
    )
    connection.close()


def _plain_text(text_type):
    return get_database_gateway().fetch_one(
        """
        select id, type, filter_type, filter_content, text, title,
               detailed_title, default_order
        from texts
        where type=? and coalesce(text, '') not like '%{{%'
        order by id
        limit 1
        """,
        (text_type,),
    )
