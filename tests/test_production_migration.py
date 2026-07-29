import json
import sqlite3
import stat
from pathlib import Path

import pytest

from scripts.cloudflare.production_migration.prepare import prepare
from scripts.cloudflare.production_migration.preflight import PreflightError


ROOT = Path(__file__).parents[1]
MIGRATIONS = ROOT / "migrations" / "d1"


def test_prepare_builds_private_reconciled_bundle(tmp_path):
    source = _build_source(tmp_path)
    _add_representative_data(source)
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"

    manifest = prepare(source, first_output, MIGRATIONS)
    prepare(source, second_output, MIGRATIONS)

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
        prepare(source, tmp_path / "output", MIGRATIONS)


def test_prepare_rejects_schema_drift(tmp_path):
    source = _build_source(tmp_path)
    connection = sqlite3.connect(source)
    try:
        connection.execute("ALTER TABLE users ADD COLUMN unexpected TEXT")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PreflightError, match="schema mismatch"):
        prepare(source, tmp_path / "output", MIGRATIONS)


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
        prepare(source, tmp_path / "output", MIGRATIONS)


def test_prepare_rejects_unknown_source_tables(tmp_path):
    source = _build_source(tmp_path)
    connection = sqlite3.connect(source)
    try:
        connection.execute("CREATE TABLE unreviewed_data (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PreflightError, match="Unknown source tables"):
        prepare(source, tmp_path / "output", MIGRATIONS)


def _build_source(tmp_path: Path) -> Path:
    path = tmp_path / "source.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            (ROOT / "ordinarium" / "schema.sql").read_text(encoding="utf-8")
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
            ) VALUES (8, 1, 1, 'Prayer', 'Text', 'stable-1');
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

    prepare(source, output, MIGRATIONS)

    manifest_text = (output / "manifest.json").read_text()
    assert "access-token" not in manifest_text
    assert "refresh-token" not in manifest_text
    assert "O'Brien" not in manifest_text
    json.loads(manifest_text)
