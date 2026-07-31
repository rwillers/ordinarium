import json
import sqlite3
import stat
from pathlib import Path

import pytest

from scripts.cloudflare.production_migration.database import apply_d1_migrations
from scripts.cloudflare.production_migration.prepare import prepare
from scripts.cloudflare.production_migration.preflight import PreflightError
from scripts.cloudflare.production_migration.source_upgrade import (
    SourceMigrationError,
    apply_pending_source_migrations,
)
from scripts.cloudflare.reconcile_d1_export import reconcile_export


ROOT = Path(__file__).parents[1]
MIGRATIONS = ROOT / "migrations" / "d1"
SOURCE_MIGRATIONS = ROOT / "scripts" / "migrations"


def test_prepare_builds_private_reconciled_bundle(tmp_path):
    source = _build_source(tmp_path)
    _add_representative_data(source)
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"

    manifest = prepare(source, first_output, MIGRATIONS, SOURCE_MIGRATIONS)
    prepare(source, second_output, MIGRATIONS, SOURCE_MIGRATIONS)

    assert manifest["preflight"] == {
        "integrity": "ok",
        "foreign_keys": "ok",
        "known_tables": "ok",
        "schema_parity": "ok",
        "pco_work_drained": "ok",
        "claims_released": "ok",
        "service_leases_drained": "ok",
    }
    assert manifest["local_rehearsal"]["status"] == "passed"
    assert manifest["source_schema_upgrade"]["applied"] == []
    assert manifest["migrated_tables"]["pco_connections"]["rows"] == 1
    assert manifest["migrated_tables"]["service_custom_templates"]["rows"] == 1
    assert manifest["excluded_tables"]["password_reset_requests"]["rows"] == 1
    assert (first_output / "production-data.sql").read_text() == (
        second_output / "production-data.sql"
    ).read_text()

    export = (first_output / "production-data.sql").read_text()
    assert "BEGIN TRANSACTION" not in export
    assert "\nCOMMIT;" not in export
    assert "PRAGMA defer_foreign_keys = true;" in export
    assert "O''Brien" in export
    for filename in (
        "source-snapshot.sqlite3",
        "production-data.sql",
        "manifest.json",
    ):
        mode = stat.S_IMODE((first_output / filename).stat().st_mode)
        assert mode == 0o600


def test_prepare_rejects_unfinished_pco_work(tmp_path):
    source = _build_source(tmp_path)
    connection = sqlite3.connect(source)
    try:
        connection.execute(
            """
            INSERT INTO pco_batch_sync_jobs (
              id, user_id, status, request_payload
            ) VALUES ('job-running', 1, 'running', '{}')
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PreflightError, match="work is not drained"):
        prepare(source, tmp_path / "output", MIGRATIONS, SOURCE_MIGRATIONS)


def test_prepare_rejects_schema_drift(tmp_path):
    source = _build_source(tmp_path)
    connection = sqlite3.connect(source)
    try:
        connection.execute("ALTER TABLE users ADD COLUMN unexpected TEXT")
        connection.commit()
    finally:
        connection.close()

    output = tmp_path / "output"
    with pytest.raises(PreflightError, match="schema mismatch"):
        prepare(source, output, MIGRATIONS, SOURCE_MIGRATIONS)
    assert not (output / ".normalized-source.sqlite3").exists()


def test_prepare_rejects_active_service_leases(tmp_path):
    source = _build_source(tmp_path)
    connection = sqlite3.connect(source)
    try:
        connection.execute(
            """
            INSERT INTO pco_service_sync_leases (
              service_id, claim_token, claim_expires_at
            ) VALUES (1, 'active-claim', 4102444800)
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PreflightError, match="service leases remain active"):
        prepare(source, tmp_path / "output", MIGRATIONS, SOURCE_MIGRATIONS)


def test_prepare_rejects_unknown_source_tables(tmp_path):
    source = _build_source(tmp_path)
    connection = sqlite3.connect(source)
    try:
        connection.execute("CREATE TABLE unreviewed_data (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PreflightError, match="Unknown source tables"):
        prepare(source, tmp_path / "output", MIGRATIONS, SOURCE_MIGRATIONS)


def _build_source(tmp_path: Path) -> Path:
    path = tmp_path / "source.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            (ROOT / "ordinarium" / "schema.sql").read_text(encoding="utf-8")
        )
        connection.executemany(
            "INSERT INTO schema_migrations (filename) VALUES (?)",
            [(path.name,) for path in sorted(SOURCE_MIGRATIONS.glob("*.sql"))],
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _add_representative_data(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            INSERT INTO pco_connections (
              user_id, access_token, refresh_token
            ) VALUES (1, 'access-token', 'refresh-token');
            INSERT INTO service_pco_links (
              id, service_id, pco_service_type_id, pco_plan_id
            ) VALUES (5, 1, 'type-1', 'plan-1');
            INSERT INTO service_pco_item_links (
              id, service_id, ordinarium_token, pco_item_id
            ) VALUES (6, 1, 'item-token', 'item-1');
            INSERT INTO pco_batch_sync_jobs (
              id, user_id, status, request_payload
            ) VALUES ('job-1', 1, 'succeeded', '{}');
            INSERT INTO pco_plan_operations (
              id, operation_key, user_id, service_id, mode,
              pco_service_type_id, status
            ) VALUES (
              'operation-1', 'operation-key', 1, 1, 'create_new',
              'type-1', 'completed'
            );
            INSERT INTO pco_batch_sync_rows (
              id, job_id, row_index, service_id, mode, request_json,
              status, plan_operation_id
            ) VALUES (
              'row-1', 'job-1', 0, 1, 'create_new', '{}',
              'success', 'operation-1'
            );
            INSERT INTO service_shares (
              id, service_id, share_uuid
            ) VALUES (7, 1, 'share-1');
            INSERT INTO service_custom_elements (
              id, service_id, user_id, title, text, stable_token
            ) VALUES (8, 1, 1, 'Prayer', 'Line 1\r\nLine 2', 'stable-1');
            INSERT INTO service_custom_templates (
              id, user_id, title, text
            ) VALUES (9, 1, 'O''Brien', 'Line 1\nLine 2');
            INSERT INTO password_reset_requests (
              id, user_id, token_hash, expires_at
            ) VALUES ('reset-1', 1, 'hash', '2099-01-01T00:00:00Z');
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_manifest_contains_no_row_values(tmp_path):
    source = _build_source(tmp_path)
    _add_representative_data(source)
    output = tmp_path / "output"

    prepare(source, output, MIGRATIONS, SOURCE_MIGRATIONS)

    manifest_text = (output / "manifest.json").read_text()
    assert "access-token" not in manifest_text
    assert "refresh-token" not in manifest_text
    assert "O'Brien" not in manifest_text
    json.loads(manifest_text)


def test_private_source_upgrade_applies_only_pending_linear_migrations(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
              id INTEGER PRIMARY KEY,
              filename TEXT UNIQUE NOT NULL
            );
            CREATE TABLE records (id INTEGER PRIMARY KEY);
            INSERT INTO schema_migrations (filename) VALUES ('001_initial.sql');
            """
        )
        connection.commit()
    finally:
        connection.close()

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_initial.sql").write_text(
        "CREATE TABLE records (id INTEGER PRIMARY KEY);"
    )
    (migrations / "002_add_name.sql").write_text(
        "ALTER TABLE records ADD COLUMN name TEXT;"
    )

    result = apply_pending_source_migrations(database, migrations)

    assert result["applied"] == ["002_add_name.sql"]
    connection = sqlite3.connect(database)
    try:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(records)")]
        assert columns == ["id", "name"]
    finally:
        connection.close()


def test_private_source_upgrade_rejects_non_linear_history(tmp_path):
    database = tmp_path / "invalid.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
              id INTEGER PRIMARY KEY,
              filename TEXT UNIQUE NOT NULL
            );
            INSERT INTO schema_migrations (filename) VALUES ('002_second.sql');
            """
        )
        connection.commit()
    finally:
        connection.close()
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_first.sql").write_text("SELECT 1;")
    (migrations / "002_second.sql").write_text("SELECT 1;")

    with pytest.raises(SourceMigrationError, match="not a contiguous prefix"):
        apply_pending_source_migrations(database, migrations)


def test_remote_d1_export_reconciles_without_retaining_row_evidence(tmp_path):
    source = _build_source(tmp_path)
    _add_representative_data(source)
    output = tmp_path / "bundle"
    prepare(source, output, MIGRATIONS, SOURCE_MIGRATIONS)

    target = sqlite3.connect(tmp_path / "remote.sqlite3")
    try:
        apply_d1_migrations(target, MIGRATIONS)
        target.executescript(
            (output / "production-data.sql").read_bytes().decode("utf-8")
        )
        target.commit()
        export_path = tmp_path / "d1-export.sql"
        export_path.write_text("\n".join(target.iterdump()) + "\n")
    finally:
        target.close()

    evidence = reconcile_export(output / "manifest.json", export_path)

    assert evidence["status"] == "passed"
    assert evidence["migrated_table_count"] == 11
    assert "tables" not in evidence
