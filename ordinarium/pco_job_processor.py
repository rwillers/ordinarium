from __future__ import annotations

import time
import uuid

from .db import get_gateway_connection
from .pco_auth import get_valid_pco_connection
from .pco_batch_jobs import (
    BATCH_ROW_TERMINAL,
    claim_pco_batch_sync_row,
    claim_pco_service_sync,
    complete_pco_batch_sync_row,
    exhaust_pco_batch_sync_row,
    get_pco_batch_sync_job,
    get_pco_batch_sync_row,
    list_pco_batch_sync_rows,
    release_pco_batch_sync_row,
    release_pco_service_sync,
)
from .pco_client import (
    PcoAuthError,
    begin_pco_request_deadline,
    end_pco_request_deadline,
)
from .pco_job_errors import (
    RetryablePcoJobError,
    TerminalPcoAuthError,
    TerminalPcoJobError,
    raise_if_retryable_pco_error,
    raise_if_terminal_pco_auth,
    raise_if_terminal_pco_error,
)
from .pco_plan_operations import PcoPlanOperationBusy
from .service_pco_routes import (
    BATCH_SYNC_MODES,
    _duplicate_batch_target_indexes,
    _execute_pco_batch_row,
    _load_batch_links,
    _load_batch_services,
    _parse_service_id,
    _to_text,
)

PROVIDER_DEADLINE_SECONDS = 90
ROW_LEASE_SECONDS = 180
SERVICE_LEASE_SECONDS = 180


def process_pco_row_message(payload, db=None):
    database = db or get_gateway_connection()
    job_id, row_id, user_id = payload["job_id"], payload["row_id"], payload["user_id"]
    row = get_pco_batch_sync_row(row_id, job_id=job_id, db=database)
    if not row:
        return _retry("row_not_found", 30)
    if row["status"] in BATCH_ROW_TERMINAL:
        return _terminal("duplicate")
    job = get_pco_batch_sync_job(job_id, user_id, db=database)
    if not job:
        return _retry("job_not_found", 30)

    claim = uuid.uuid4().hex
    now = int(time.time())
    if not claim_pco_batch_sync_row(
        job_id,
        row_id,
        user_id,
        claim,
        now + ROW_LEASE_SECONDS,
        now_epoch=now,
        db=database,
    ):
        current = get_pco_batch_sync_row(row_id, job_id=job_id, db=database)
        if current and current["status"] in BATCH_ROW_TERMINAL:
            return _terminal("duplicate")
        return _retry("row_lease_active", 20)

    service_claim = None
    deadline_token = begin_pco_request_deadline(PROVIDER_DEADLINE_SECONDS)
    try:
        connection = get_valid_pco_connection(user_id, database)
        if not connection:
            return _complete_terminal_failure(
                database, row, claim, "Planning Center is not connected.", "auth"
            )
        prepared, terminal_result = _prepare_row(database, job, row)
        if terminal_result:
            return _complete_result(database, row, claim, terminal_result)

        service_claim = uuid.uuid4().hex
        service_claimed_at = int(time.time())
        if not claim_pco_service_sync(
            prepared["service_id"],
            service_claim,
            service_claimed_at + SERVICE_LEASE_SECONDS,
            now_epoch=service_claimed_at,
            db=database,
        ):
            raise RetryablePcoJobError(
                "Planning Center service sync is already in progress.",
                category="lease",
                retry_after_seconds=20,
            )

        services = _load_batch_services(database, user_id, [prepared["service_id"]])
        all_rows = _prepared_rows(list_pco_batch_sync_rows(job_id, db=database))
        service_ids = [item["service_id"] for item in all_rows if item["service_id"]]
        links = _load_batch_links(database, service_ids)
        duplicate_indexes = _duplicate_batch_target_indexes(
            all_rows,
            {},
            services | _load_batch_services(database, user_id, service_ids),
            links,
        )
        plan_context = {}
        result = _execute_pco_batch_row(
            prepared,
            user_id,
            connection["access_token"],
            _application_config("PCO_API_BASE"),
            _to_text(job["request_payload"].get("pco_plan_time")) or "10:00",
            _to_text(job["request_payload"].get("pco_plan_tz_offset")),
            database,
            _load_batch_services(database, user_id, service_ids),
            links,
            duplicate_indexes,
            propagate_retryable=True,
            durable_plan_context=plan_context,
        )
        return _complete_result(database, row, claim, result, plan_context)
    except PcoPlanOperationBusy as exc:
        return _release_for_retry(database, row, claim, "lease", str(exc), 20)
    except RetryablePcoJobError as exc:
        return _release_for_retry(
            database,
            row,
            claim,
            exc.category,
            str(exc),
            exc.retry_after_seconds,
        )
    except PcoAuthError as exc:
        if "in progress" in str(exc).lower() or "lease was lost" in str(exc).lower():
            return _release_for_retry(
                database, row, claim, "auth_refresh", str(exc), 20
            )
        return _complete_terminal_failure(database, row, claim, str(exc), "auth")
    except TerminalPcoAuthError as exc:
        return _complete_terminal_failure(database, row, claim, str(exc), "auth")
    except Exception as exc:
        try:
            raise_if_retryable_pco_error(exc)
        except RetryablePcoJobError as retryable:
            return _release_for_retry(
                database,
                row,
                claim,
                retryable.category,
                str(retryable),
                retryable.retry_after_seconds,
            )
        try:
            raise_if_terminal_pco_auth(exc)
        except TerminalPcoAuthError as terminal:
            return _complete_terminal_failure(
                database, row, claim, str(terminal), "auth"
            )
        try:
            raise_if_terminal_pco_error(exc)
        except TerminalPcoJobError as terminal:
            return _complete_terminal_failure(
                database, row, claim, str(terminal), terminal.category
            )
        return _release_for_retry(database, row, claim, "internal", str(exc), 30)
    finally:
        end_pco_request_deadline(deadline_token)
        if service_claim and row.get("service_id"):
            release_pco_service_sync(row["service_id"], service_claim, db=database)


def dead_letter_pco_row_message(payload, db=None):
    database = db or get_gateway_connection()
    persisted = exhaust_pco_batch_sync_row(
        payload["job_id"], payload["row_id"], payload["user_id"], db=database
    )
    if not persisted:
        return _retry("d1_unavailable", 30)
    return _terminal("retry_exhausted")


def _prepare_row(db, job, row):
    raw = row.get("request")
    if not isinstance(raw, dict):
        return None, _failure_result(row, "Invalid row payload.")
    prepared = _prepared_row(row["row_index"], raw)
    if not prepared["service_id"]:
        return None, _failure_result(row, "Service ID is required.")
    if prepared["mode"] not in BATCH_SYNC_MODES:
        return None, _failure_result(row, "Invalid batch mode.")
    if prepared["mode"] == "skip":
        result = _base_result(row)
        result["status"] = "skipped"
        return None, result
    return prepared, None


def _prepared_rows(rows):
    return [_prepared_row(row["row_index"], row.get("request") or {}) for row in rows]


def _prepared_row(index, raw):
    return {
        "index": index,
        "service_id": _parse_service_id(raw.get("service_id")),
        "mode": _to_text(raw.get("mode")),
        "pco_service_type_id": _to_text(raw.get("pco_service_type_id")),
        "pco_service_type_name": _to_text(raw.get("pco_service_type_name")),
        "pco_plan_id": _to_text(raw.get("pco_plan_id")),
        "pco_plan_template_id": _to_text(raw.get("pco_plan_template_id")),
    }


def _complete_result(db, row, claim, result, plan_context=None):
    status = result.get("status")
    if status not in {"success", "failed", "skipped"}:
        return _release_for_retry(db, row, claim, "internal", "Invalid result.", 30)
    persisted = complete_pco_batch_sync_row(
        row["job_id"],
        row["id"],
        status,
        result,
        claim_token=claim,
        error_category=None if status != "failed" else "validation",
        effective_service_type_id=result.get("pco_service_type_id"),
        effective_plan_id=result.get("pco_plan_id"),
        plan_operation_id=(plan_context or {}).get("plan_operation_id"),
        db=db,
    )
    return _terminal("completed") if persisted else _retry("d1_conflict", 20)


def _complete_terminal_failure(db, row, claim, message, category):
    result = _failure_result(row, message)
    persisted = complete_pco_batch_sync_row(
        row["job_id"],
        row["id"],
        "failed",
        result,
        claim_token=claim,
        error_category=category,
        db=db,
    )
    return _terminal(category) if persisted else _retry("d1_conflict", 20)


def _release_for_retry(db, row, claim, category, message, delay):
    persisted = release_pco_batch_sync_row(
        row["job_id"], row["id"], claim, error_category=category, db=db
    )
    if not persisted:
        return _retry("d1_conflict", 20)
    return _retry(category, delay, message)


def _failure_result(row, message):
    result = _base_result(row)
    result.update({"status": "failed", "error": message})
    return result


def _base_result(row):
    return {"service_id": row["service_id"], "mode": row["mode"], "error": ""}


def _terminal(reason):
    return {"disposition": "terminal", "persisted": True, "reason": reason}, 200


def _retry(reason, delay, message=None):
    body = {
        "disposition": "retry",
        "persisted": False,
        "reason": reason,
        "retry_after_seconds": int(delay),
    }
    if message:
        body["error"] = message
    return body, 429 if reason == "rate_limit" else 503


def _application_config(name):
    from flask import current_app

    return current_app.config.get(name)
