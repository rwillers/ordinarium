from __future__ import annotations

import json
import time
import uuid
from datetime import datetime

from .db import get_database_gateway
from .infrastructure import DatabaseStatement

BATCH_JOB_QUEUED = "queued"
BATCH_JOB_RUNNING = "running"
BATCH_JOB_SUCCEEDED = "succeeded"
BATCH_JOB_FAILED = "failed"

BATCH_ROW_PENDING = "pending"
BATCH_ROW_RUNNING = "running"
BATCH_ROW_RETRY = "retry"
BATCH_ROW_SUCCESS = "success"
BATCH_ROW_FAILED = "failed"
BATCH_ROW_SKIPPED = "skipped"
BATCH_ROW_TERMINAL = {BATCH_ROW_SUCCESS, BATCH_ROW_FAILED, BATCH_ROW_SKIPPED}


def _utc_now():
    return datetime.utcnow().isoformat()


def create_pco_batch_sync_job(user_id, payload, db=None):
    """Atomically create a batch job and stable, ordered row records."""
    database = _database(db)
    job_id = uuid.uuid4().hex
    now = _utc_now()
    rows = payload.get("rows") if isinstance(payload, dict) else []
    rows = rows if isinstance(rows, list) else []
    statements = [
        DatabaseStatement(
            """
            insert into pco_batch_sync_jobs (
              id, user_id, status, request_payload, results_json, summary_json,
              created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                user_id,
                BATCH_JOB_QUEUED,
                json.dumps(payload),
                json.dumps([]),
                json.dumps(_empty_summary(payload)),
                now,
                now,
            ),
        )
    ]
    for row_index, raw_row in enumerate(rows):
        row = raw_row if isinstance(raw_row, dict) else {}
        statements.append(
            DatabaseStatement(
                """
                insert into pco_batch_sync_rows (
                  id, job_id, row_index, service_id, mode, request_json,
                  status, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    job_id,
                    row_index,
                    _service_id(row.get("service_id")),
                    _text(row.get("mode")),
                    json.dumps(raw_row),
                    BATCH_ROW_PENDING,
                    now,
                    now,
                ),
            )
        )
    _batch(database, statements)
    return job_id


def get_pco_batch_sync_job(job_id, user_id, db=None):
    if not job_id or not user_id:
        return None
    database = _database(db)
    row = _fetch_one(
        database,
        """
        select
          id, user_id, status, request_payload, results_json, summary_json,
          error, created_at, updated_at, started_at, completed_at
        from pco_batch_sync_jobs
        where id=? and user_id=?
        limit 1
        """,
        (job_id, user_id),
    )
    if not row:
        return None
    job = _job_from_row(row)
    durable_rows = list_pco_batch_sync_rows(job_id, db=database)
    if durable_rows:
        job.update(_aggregate_rows(durable_rows, job))
    return job


def list_pco_batch_sync_rows(job_id, db=None):
    if not job_id:
        return []
    rows = _fetch_all(
        _database(db),
        """
        select
          id, job_id, row_index, service_id, mode, request_json, status,
          effective_service_type_id, effective_plan_id, plan_operation_id,
          claim_token, claim_expires_at, result_json, error_category,
          created_at, updated_at, completed_at
        from pco_batch_sync_rows
        where job_id=?
        order by row_index, id
        """,
        (job_id,),
    )
    return [_batch_row_from_record(row) for row in rows]


def get_pco_batch_sync_row(row_id, job_id=None, db=None):
    if not row_id:
        return None
    database = _database(db)
    if job_id:
        row = _fetch_one(
            database,
            "select * from pco_batch_sync_rows where id=? and job_id=? limit 1",
            (row_id, job_id),
        )
    else:
        row = _fetch_one(
            database,
            "select * from pco_batch_sync_rows where id=? limit 1",
            (row_id,),
        )
    return _batch_row_from_record(row) if row else None


def claim_pco_batch_sync_row(
    job_id,
    row_id,
    user_id,
    claim_token,
    claim_expires_at,
    *,
    now_epoch=None,
    db=None,
):
    """Claim a pending/retry row or safely take over an expired claim."""
    if not all((job_id, row_id, user_id, claim_token, claim_expires_at)):
        return False
    now_epoch = int(now_epoch if now_epoch is not None else time.time())
    cursor = _execute(
        _database(db),
        """
        update pco_batch_sync_rows set
          status=?, claim_token=?, claim_expires_at=?, updated_at=?
        where id=? and job_id=?
          and exists (
            select 1 from pco_batch_sync_jobs
            where id=? and user_id=?
          )
          and (
            status in (?, ?)
            or (status=? and coalesce(claim_expires_at, 0) <= ?)
          )
        """,
        (
            BATCH_ROW_RUNNING,
            claim_token,
            int(claim_expires_at),
            _utc_now(),
            row_id,
            job_id,
            job_id,
            user_id,
            BATCH_ROW_PENDING,
            BATCH_ROW_RETRY,
            BATCH_ROW_RUNNING,
            now_epoch,
        ),
    )
    if _changes(cursor) != 1:
        return False
    mark_pco_batch_sync_job_running(job_id, db=db)
    return True


def release_pco_batch_sync_row(
    job_id, row_id, claim_token, *, error_category=None, db=None
):
    """Release a claimed row for retry without making it terminal."""
    cursor = _execute(
        _database(db),
        """
        update pco_batch_sync_rows set
          status=?, claim_token=null, claim_expires_at=null,
          error_category=?, updated_at=?
        where id=? and job_id=? and status=? and claim_token=?
        """,
        (
            BATCH_ROW_RETRY,
            error_category,
            _utc_now(),
            row_id,
            job_id,
            BATCH_ROW_RUNNING,
            claim_token,
        ),
    )
    return _changes(cursor) == 1


def claim_pco_service_sync(
    service_id, claim_token, claim_expires_at, *, now_epoch=None, db=None
):
    """Serialize provider mutations for one Ordinarium service across deliveries."""
    if not service_id or not claim_token:
        return False
    now_epoch = int(now_epoch if now_epoch is not None else time.time())
    cursor = _execute(
        _database(db),
        """
        insert into pco_service_sync_leases (
          service_id, claim_token, claim_expires_at, updated_at
        ) values (?, ?, ?, CURRENT_TIMESTAMP)
        on conflict(service_id) do update set
          claim_token=excluded.claim_token,
          claim_expires_at=excluded.claim_expires_at,
          updated_at=CURRENT_TIMESTAMP
        where pco_service_sync_leases.claim_expires_at <= ?
        """,
        (service_id, claim_token, int(claim_expires_at), now_epoch),
    )
    return _changes(cursor) == 1


def release_pco_service_sync(service_id, claim_token, db=None):
    cursor = _execute(
        _database(db),
        "delete from pco_service_sync_leases where service_id=? and claim_token=?",
        (service_id, claim_token),
    )
    return _changes(cursor) == 1


def exhaust_pco_batch_sync_row(job_id, row_id, user_id, db=None):
    """Terminalize an exhausted queue delivery without overwriting completed work."""
    row = get_pco_batch_sync_row(row_id, job_id=job_id, db=db)
    if not row:
        return False
    if row["status"] in BATCH_ROW_TERMINAL:
        return True
    terminal_claim = None
    if row["status"] == BATCH_ROW_RUNNING:
        if int(row.get("claim_expires_at") or 0) > int(time.time()):
            return False
        terminal_claim = row.get("claim_token")
    job = get_pco_batch_sync_job(job_id, user_id, db=db)
    if not job:
        return False
    result = {
        "service_id": row["service_id"],
        "mode": row["mode"],
        "status": BATCH_ROW_FAILED,
        "error": "Planning Center sync retries were exhausted.",
    }
    return complete_pco_batch_sync_row(
        job_id,
        row_id,
        BATCH_ROW_FAILED,
        result,
        claim_token=terminal_claim,
        error_category="retry_exhausted",
        db=db,
    )


def complete_pco_batch_sync_row(
    job_id,
    row_id,
    status,
    result,
    *,
    claim_token=None,
    error_category=None,
    effective_service_type_id=None,
    effective_plan_id=None,
    plan_operation_id=None,
    db=None,
):
    """Terminalize a row once; duplicate deliveries cannot overwrite its result."""
    if status not in BATCH_ROW_TERMINAL:
        raise ValueError("PCO batch row terminal status is invalid.")
    database = _database(db)
    claim_sql = "status=? and claim_token=?" if claim_token else "status in (?, ?)"
    params = [
        status,
        json.dumps(result),
        error_category,
        effective_service_type_id,
        effective_plan_id,
        plan_operation_id,
        _utc_now(),
        _utc_now(),
        row_id,
        job_id,
    ]
    if claim_token:
        params.extend((BATCH_ROW_RUNNING, claim_token))
    else:
        params.extend((BATCH_ROW_PENDING, BATCH_ROW_RETRY))
    cursor = _execute(
        database,
        f"""
        update pco_batch_sync_rows set
          status=?, result_json=?, error_category=?,
          effective_service_type_id=coalesce(?, effective_service_type_id),
          effective_plan_id=coalesce(?, effective_plan_id),
          plan_operation_id=coalesce(?, plan_operation_id),
          claim_token=null, claim_expires_at=null,
          updated_at=?, completed_at=?
        where id=? and job_id=? and {claim_sql}
        """,
        tuple(params),
    )
    refresh_pco_batch_sync_job(job_id, db=database)
    return _changes(cursor) == 1


def list_recoverable_pco_batch_sync_rows(
    *, stale_before, now_epoch=None, limit=100, db=None
):
    """List outbox-gap rows and expired claims; Queue owns retry backoff."""
    now_epoch = int(now_epoch if now_epoch is not None else time.time())
    rows = _fetch_all(
        _database(db),
        """
        select r.id as row_id, r.job_id, j.user_id, r.status,
               r.row_index, r.updated_at, r.claim_expires_at
        from pco_batch_sync_rows r
        join pco_batch_sync_jobs j on j.id=r.job_id
        where (
          (r.status=? and r.updated_at <= ?)
          or (r.status=? and coalesce(r.claim_expires_at, 0) <= ?)
        )
          and j.status != ?
        order by r.updated_at, r.row_index, r.id
        limit ?
        """,
        (
            BATCH_ROW_PENDING,
            stale_before,
            BATCH_ROW_RUNNING,
            now_epoch,
            BATCH_JOB_FAILED,
            int(limit),
        ),
    )
    return [dict(row) for row in rows]


def refresh_pco_batch_sync_job(job_id, db=None):
    database = _database(db)
    row = _fetch_one(
        database,
        "select * from pco_batch_sync_jobs where id=? limit 1",
        (job_id,),
    )
    if not row:
        return None
    job = _job_from_row(row)
    rows = list_pco_batch_sync_rows(job_id, db=database)
    if not rows:
        return job
    aggregate = _aggregate_rows(rows, job)
    terminal = aggregate["status"] == BATCH_JOB_SUCCEEDED
    _execute(
        database,
        """
        update pco_batch_sync_jobs set
          status=?, results_json=?, summary_json=?, error=null,
          updated_at=?, completed_at=case when ? then coalesce(completed_at, ?) else null end
        where id=? and status != ?
        """,
        (
            aggregate["status"],
            json.dumps(aggregate["results"]),
            json.dumps(aggregate["summary"]),
            _utc_now(),
            terminal,
            _utc_now(),
            job_id,
            BATCH_JOB_FAILED,
        ),
    )
    job.update(aggregate)
    return job


def mark_pco_batch_sync_job_running(job_id, db=None):
    now = _utc_now()
    _execute(
        _database(db),
        """
        update pco_batch_sync_jobs set
          status=?, started_at=coalesce(started_at, ?), updated_at=?
        where id=? and status=?
        """,
        (BATCH_JOB_RUNNING, now, now, job_id, BATCH_JOB_QUEUED),
    )


def update_pco_batch_sync_job_results(job_id, results, summary, db=None):
    _execute(
        _database(db),
        """
        update pco_batch_sync_jobs set
          results_json=?, summary_json=?, updated_at=?
        where id=?
        """,
        (json.dumps(results), json.dumps(summary), _utc_now(), job_id),
    )


def complete_pco_batch_sync_job(job_id, results, summary, db=None):
    now = _utc_now()
    _execute(
        _database(db),
        """
        update pco_batch_sync_jobs set
          status=?, results_json=?, summary_json=?, error=null,
          updated_at=?, completed_at=?
        where id=?
        """,
        (
            BATCH_JOB_SUCCEEDED,
            json.dumps(results),
            json.dumps(summary),
            now,
            now,
            job_id,
        ),
    )


def fail_pco_batch_sync_job(job_id, error, db=None):
    now = _utc_now()
    _execute(
        _database(db),
        """
        update pco_batch_sync_jobs set
          status=?, error=?, updated_at=?, completed_at=?
        where id=?
        """,
        (BATCH_JOB_FAILED, str(error), now, now, job_id),
    )


def _aggregate_rows(rows, job):
    results = [_result_for_row(row) for row in rows]
    summary = {"total": len(rows), "success": 0, "failed": 0, "skipped": 0}
    for result in results:
        status = result["status"]
        if status in (BATCH_ROW_SUCCESS, BATCH_ROW_FAILED, BATCH_ROW_SKIPPED):
            summary[status] += 1
    all_terminal = all(row["status"] in BATCH_ROW_TERMINAL for row in rows)
    any_started = any(row["status"] != BATCH_ROW_PENDING for row in rows)
    if job["status"] == BATCH_JOB_FAILED:
        status = BATCH_JOB_FAILED
    elif all_terminal:
        status = BATCH_JOB_SUCCEEDED
    else:
        status = BATCH_JOB_RUNNING if any_started else BATCH_JOB_QUEUED
    completed_at = job["completed_at"]
    if all_terminal and not completed_at:
        completed_at = max(row["completed_at"] or row["updated_at"] for row in rows)
    return {
        "status": status,
        "results": results,
        "summary": summary,
        "completed_at": completed_at,
        "updated_at": max(row["updated_at"] for row in rows),
    }


def _result_for_row(row):
    request_data = row["request"] if isinstance(row["request"], dict) else {}
    result = {
        "service_id": row["service_id"],
        "mode": row["mode"],
        "status": row["status"],
        "error": "",
    }
    result.update(_loads_json(row.get("result_json"), {}))
    result["status"] = row["status"]
    result.setdefault("service_id", _service_id(request_data.get("service_id")))
    result.setdefault("mode", _text(request_data.get("mode")))
    return result


def _batch_row_from_record(row):
    record = dict(row)
    record["request"] = _loads_json(record.get("request_json"), {})
    record["result"] = _loads_json(record.get("result_json"), None)
    return record


def _empty_summary(payload):
    rows = payload.get("rows") if isinstance(payload, dict) else []
    total = len(rows) if isinstance(rows, list) else 0
    return {"total": total, "success": 0, "failed": 0, "skipped": 0}


def _job_from_row(row):
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "status": row["status"],
        "request_payload": _loads_json(row["request_payload"], {}),
        "results": _loads_json(row["results_json"], []),
        "summary": _loads_json(row["summary_json"], _empty_summary({})),
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


def _database(db):
    return db or get_database_gateway()


def _fetch_one(db, sql, params=()):
    if hasattr(db, "fetch_one"):
        return db.fetch_one(sql, params)
    return db.execute(sql, params).fetchone()


def _fetch_all(db, sql, params=()):
    if hasattr(db, "fetch_all"):
        return db.fetch_all(sql, params)
    return db.execute(sql, params).fetchall()


def _execute(db, sql, params=()):
    return db.execute(sql, params)


def _batch(db, statements):
    if hasattr(db, "batch"):
        return db.batch(statements)
    for statement in statements:
        db.execute(statement.sql, statement.params)
    return []


def _changes(cursor):
    if hasattr(cursor, "changes"):
        return cursor.changes
    return cursor.rowcount


def _loads_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _service_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value):
    return "" if value is None else str(value).strip()
