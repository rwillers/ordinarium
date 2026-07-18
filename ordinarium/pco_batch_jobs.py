from __future__ import annotations

import json
import uuid
from datetime import datetime

from .db import get_gateway_connection

BATCH_JOB_QUEUED = "queued"
BATCH_JOB_RUNNING = "running"
BATCH_JOB_SUCCEEDED = "succeeded"
BATCH_JOB_FAILED = "failed"


def _utc_now():
    return datetime.utcnow().isoformat()


def create_pco_batch_sync_job(user_id, payload, db=None):
    db = db or get_gateway_connection()
    job_id = uuid.uuid4().hex
    now = _utc_now()
    db.execute(
        """
        insert into pco_batch_sync_jobs (
          id,
          user_id,
          status,
          request_payload,
          results_json,
          summary_json,
          created_at,
          updated_at
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
    return job_id


def get_pco_batch_sync_job(job_id, user_id, db=None):
    if not job_id or not user_id:
        return None
    db = db or get_gateway_connection()
    row = db.execute(
        """
        select
          id,
          user_id,
          status,
          request_payload,
          results_json,
          summary_json,
          error,
          created_at,
          updated_at,
          started_at,
          completed_at
        from pco_batch_sync_jobs
        where id=? and user_id=?
        limit 1
        """,
        (job_id, user_id),
    ).fetchone()
    if not row:
        return None
    return _job_from_row(row)


def mark_pco_batch_sync_job_running(job_id, db=None):
    db = db or get_gateway_connection()
    now = _utc_now()
    db.execute(
        """
        update pco_batch_sync_jobs set
          status=?,
          started_at=coalesce(started_at, ?),
          updated_at=?
        where id=?
        """,
        (BATCH_JOB_RUNNING, now, now, job_id),
    )


def update_pco_batch_sync_job_results(job_id, results, summary, db=None):
    db = db or get_gateway_connection()
    db.execute(
        """
        update pco_batch_sync_jobs set
          results_json=?,
          summary_json=?,
          updated_at=?
        where id=?
        """,
        (json.dumps(results), json.dumps(summary), _utc_now(), job_id),
    )


def complete_pco_batch_sync_job(job_id, results, summary, db=None):
    db = db or get_gateway_connection()
    now = _utc_now()
    db.execute(
        """
        update pco_batch_sync_jobs set
          status=?,
          results_json=?,
          summary_json=?,
          error=null,
          updated_at=?,
          completed_at=?
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
    db = db or get_gateway_connection()
    now = _utc_now()
    db.execute(
        """
        update pco_batch_sync_jobs set
          status=?,
          error=?,
          updated_at=?,
          completed_at=?
        where id=?
        """,
        (BATCH_JOB_FAILED, str(error), now, now, job_id),
    )


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


def _loads_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback
