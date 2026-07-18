import sqlite3
from pathlib import Path

from scripts.cloudflare.generate_d1_baseline import generate


ROOT = Path(__file__).parents[1]
MIGRATIONS = ROOT / "migrations" / "d1"


def test_generated_d1_baseline_is_current(tmp_path):
    generate(tmp_path)

    assert (tmp_path / "0001_baseline.sql").read_text() == (
        MIGRATIONS / "0001_baseline.sql"
    ).read_text()
    assert (tmp_path / "0002_reference_data.sql").read_text() == (
        MIGRATIONS / "0002_reference_data.sql"
    ).read_text()


def test_d1_migrations_apply_to_clean_sqlite():
    connection = sqlite3.connect(":memory:")
    try:
        for path in sorted(MIGRATIONS.glob("*.sql")):
            connection.executescript(path.read_text(encoding="utf-8"))

        counts = {
            table: connection.execute(f"select count(*) from {table}").fetchone()[0]
            for table in ("holidays", "fragments", "subcycles", "pages", "texts")
        }
        assert all(count > 0 for count in counts.values())
        assert connection.execute("select count(*) from users").fetchone()[0] == 0
        assert connection.execute("select count(*) from services").fetchone()[0] == 0
        assert (
            connection.execute(
                "select next_value from id_sequences where name='users'"
            ).fetchone()[0]
            == 1
        )
    finally:
        connection.close()


def test_sqlite_id_sequence_migration_starts_after_existing_ids():
    connection = sqlite3.connect(":memory:")
    try:
        for table in (
            "users",
            "services",
            "service_shares",
            "service_custom_elements",
            "service_custom_templates",
            "service_pco_links",
            "service_pco_item_links",
        ):
            connection.execute(f"create table {table} (id integer primary key)")
        connection.execute("insert into users (id) values (9)")
        connection.execute("insert into services (id) values (14)")

        migration = ROOT / "scripts" / "migrations" / "040_add_id_sequences.sql"
        connection.executescript(migration.read_text(encoding="utf-8"))

        values = dict(connection.execute("select name, next_value from id_sequences"))
        assert values["users"] == 10
        assert values["services"] == 15
        assert values["service_shares"] == 1

        connection.execute("insert into services (id) values (27)")
        next_service_id = connection.execute(
            "select next_value from id_sequences where name='services'"
        ).fetchone()[0]
        assert next_service_id == 28
    finally:
        connection.close()
