import json
import sqlite3
from pathlib import Path

from ordinarium.db import get_gateway_connection
from ordinarium.pco_batch_jobs import (
    claim_pco_batch_sync_row,
    complete_pco_batch_sync_row,
    create_pco_batch_sync_job,
    fail_pco_batch_sync_job,
    get_pco_batch_sync_job,
    list_pco_batch_sync_rows,
    list_recoverable_pco_batch_sync_rows,
    release_pco_batch_sync_row,
)


def _batch_payload():
    return {
        "rows": [
            {"service_id": 12, "mode": "skip"},
            {"service_id": 13, "mode": "sync_linked"},
        ],
        "pco_plan_time": "10:00",
        "pco_plan_tz_offset": "0",
    }


def test_batch_job_creates_stable_ordered_rows(app, user_factory):
    user_id = user_factory()
    with app.app_context():
        db = get_gateway_connection()
        job_id = create_pco_batch_sync_job(user_id, _batch_payload(), db=db)
        first_read = list_pco_batch_sync_rows(job_id, db=db)
        second_read = list_pco_batch_sync_rows(job_id, db=db)

    assert [row["row_index"] for row in first_read] == [0, 1]
    assert [row["id"] for row in first_read] == [row["id"] for row in second_read]
    assert first_read[0]["request"] == {"service_id": 12, "mode": "skip"}
    assert first_read[1]["service_id"] == 13


def test_row_completion_is_duplicate_safe_and_aggregates_failures_as_successful_job(
    app, user_factory
):
    user_id = user_factory()
    with app.app_context():
        db = get_gateway_connection()
        job_id = create_pco_batch_sync_job(user_id, _batch_payload(), db=db)
        rows = list_pco_batch_sync_rows(job_id, db=db)
        assert claim_pco_batch_sync_row(
            job_id,
            rows[0]["id"],
            user_id,
            "claim-a",
            200,
            now_epoch=100,
            db=db,
        )
        assert not complete_pco_batch_sync_row(
            job_id,
            rows[0]["id"],
            "failed",
            {"status": "failed", "error": "wrong worker"},
            claim_token="claim-other",
            db=db,
        )
        assert complete_pco_batch_sync_row(
            job_id,
            rows[0]["id"],
            "skipped",
            {"service_id": 12, "mode": "skip", "status": "skipped"},
            claim_token="claim-a",
            db=db,
        )
        assert not complete_pco_batch_sync_row(
            job_id,
            rows[0]["id"],
            "failed",
            {"status": "failed", "error": "duplicate overwrote result"},
            db=db,
        )
        assert complete_pco_batch_sync_row(
            job_id,
            rows[1]["id"],
            "failed",
            {
                "service_id": 13,
                "mode": "sync_linked",
                "status": "failed",
                "error": "terminal validation",
            },
            db=db,
        )
        job = get_pco_batch_sync_job(job_id, user_id, db=db)

    assert job["status"] == "succeeded"
    assert job["summary"] == {"total": 2, "success": 0, "failed": 1, "skipped": 1}
    assert [result["status"] for result in job["results"]] == ["skipped", "failed"]
    assert job["results"][0].get("error") != "duplicate overwrote result"


def test_job_wide_failure_is_not_hidden_by_terminal_rows(app, user_factory):
    user_id = user_factory()
    with app.app_context():
        db = get_gateway_connection()
        job_id = create_pco_batch_sync_job(user_id, _batch_payload(), db=db)
        rows = list_pco_batch_sync_rows(job_id, db=db)
        for row in rows:
            complete_pco_batch_sync_row(
                job_id,
                row["id"],
                "skipped",
                {
                    "service_id": row["service_id"],
                    "mode": row["mode"],
                    "status": "skipped",
                },
                db=db,
            )
        fail_pco_batch_sync_job(job_id, "job infrastructure failed", db=db)
        job = get_pco_batch_sync_job(job_id, user_id, db=db)

    assert job["status"] == "failed"
    assert job["error"] == "job infrastructure failed"


def test_queue_recovery_excludes_retry_and_includes_expired_claim(app, user_factory):
    user_id = user_factory()
    with app.app_context():
        db = get_gateway_connection()
        job_id = create_pco_batch_sync_job(user_id, _batch_payload(), db=db)
        rows = list_pco_batch_sync_rows(job_id, db=db)
        assert claim_pco_batch_sync_row(
            job_id,
            rows[0]["id"],
            user_id,
            "claim-retry",
            200,
            now_epoch=100,
            db=db,
        )
        assert release_pco_batch_sync_row(
            job_id,
            rows[0]["id"],
            "claim-retry",
            error_category="network",
            db=db,
        )
        assert claim_pco_batch_sync_row(
            job_id,
            rows[1]["id"],
            user_id,
            "claim-expired",
            120,
            now_epoch=100,
            db=db,
        )
        recoverable = list_recoverable_pco_batch_sync_rows(
            stale_before="9999-12-31T23:59:59",
            now_epoch=121,
            db=db,
        )

    assert [(row["row_id"], row["user_id"]) for row in recoverable] == [
        (rows[1]["id"], user_id),
    ]


def test_sqlite_and_d1_pco_operational_schema_are_aligned(app):
    d1_sql = (
        Path(__file__).parents[1] / "migrations" / "d1" / "0004_operational_state.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE pco_batch_sync_rows" in d1_sql

    connection = sqlite3.connect(app.config["DATABASE"])
    try:
        canonical_columns = {
            row[1]
            for row in connection.execute("pragma table_info(pco_batch_sync_rows)")
        }
        d1_connection = sqlite3.connect(":memory:")
        try:
            for table in ("users", "services", "pco_batch_sync_jobs"):
                d1_connection.execute(f"create table {table} (id integer primary key)")
            d1_connection.execute(
                "create table service_custom_elements (id integer primary key)"
            )
            d1_connection.execute(
                "create table pco_connections (user_id integer primary key)"
            )
            d1_connection.executescript(d1_sql)
            d1_columns = {
                row[1]
                for row in d1_connection.execute(
                    "pragma table_info(pco_batch_sync_rows)"
                )
            }
        finally:
            d1_connection.close()
    finally:
        connection.close()

    assert canonical_columns == d1_columns
    assert {"claim_token", "claim_expires_at", "result_json"} <= canonical_columns


def test_operational_state_migration_matches_canonical_row_shape():
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            """
            pragma foreign_keys=on;
            create table users (id integer primary key);
            create table services (id integer primary key);
            create table service_custom_elements (id integer primary key);
            create table pco_connections (user_id integer primary key);
            create table pco_batch_sync_jobs (id text primary key);
            """
        )
        migration = (
            Path(__file__).parents[1]
            / "scripts"
            / "migrations"
            / "041_add_pco_operational_state.sql"
        )
        connection.executescript(migration.read_text(encoding="utf-8"))
        columns = {
            row[1]
            for row in connection.execute("pragma table_info(pco_batch_sync_rows)")
        }
    finally:
        connection.close()

    assert "request_json" in columns
    assert "plan_operation_id" in columns


def test_row_request_json_contains_original_payload_only(app, user_factory):
    user_id = user_factory()
    with app.app_context():
        db = get_gateway_connection()
        job_id = create_pco_batch_sync_job(user_id, _batch_payload(), db=db)
        raw = db.execute(
            "select request_json from pco_batch_sync_rows where job_id=? and row_index=0",
            (job_id,),
        ).fetchone()

    assert json.loads(raw["request_json"]) == {"service_id": 12, "mode": "skip"}
