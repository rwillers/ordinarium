from __future__ import annotations

import hashlib
import json
import time
import uuid

from .pco_job_errors import (
    RetryablePcoJobError,
    TerminalPcoAuthError,
    TerminalPcoJobError,
    raise_if_retryable_pco_error,
    raise_if_terminal_pco_auth,
    raise_if_terminal_pco_error,
)
from .pco_sync import (
    PcoSyncError,
    _build_plan_time_range,
    create_plan,
    create_plan_time,
    import_plan_template,
    list_plan_times,
    list_plans_by_title,
)

PLAN_OPERATION_LEASE_SECONDS = 180


def complete_pco_plan_operation(
    *,
    db,
    user_id,
    service_id,
    access_token,
    base_url,
    values,
    lease_seconds=PLAN_OPERATION_LEASE_SECONDS,
):
    """Complete a create-plan step machine that reconciles uncertain POST results."""
    operation = _ensure_operation(db, user_id, service_id, values)
    if operation["status"] == "completed":
        return _operation_result(operation)
    claim = _claim_operation(db, operation["id"], lease_seconds)
    if not claim:
        raise PcoPlanOperationBusy("Planning Center plan setup is already in progress.")
    try:
        operation = _get_operation(db, operation["operation_key"])
        operation = _complete_claimed_operation(
            db, operation, claim, access_token, base_url, values
        )
        return _operation_result(operation)
    except Exception as exc:
        _mark_operation_retry(db, operation["id"], claim, exc)
        raise
    finally:
        _release_operation(db, operation["id"], claim)


class PcoPlanOperationBusy(PcoSyncError):
    pass


def _complete_claimed_operation(db, operation, claim, token, base_url, values):
    plan_id = operation.get("pco_plan_id")
    plan_title = operation.get("pco_plan_title") or values["plan_title"]
    if not plan_id:
        operation = _ensure_baseline(db, operation, claim, token, base_url, values)
        reconciled = _reconcile_created_plan(operation, token, base_url, values)
        if reconciled:
            plan_id = str(reconciled["id"])
            plan_title = (reconciled.get("attributes") or {}).get("title") or plan_title
        else:
            _renew_operation(db, operation["id"], claim)
            created = create_plan(
                base_url,
                token,
                values["service_type_id"],
                values["plan_title"],
                values["plan_date"],
                values.get("series_title"),
            )
            data = (created or {}).get("data") or {}
            plan_id = str(data.get("id") or "")
            plan_title = (data.get("attributes") or {}).get("title") or plan_title
            if not plan_id:
                raise PcoSyncError("PCO plan creation failed.")
        _advance_operation(
            db,
            operation["id"],
            claim,
            "plan_created",
            plan_id=plan_id,
            plan_title=plan_title,
        )
        operation = _get_operation(db, operation["operation_key"])

    if _step_rank(operation.get("step")) < _step_rank("time_created"):
        _renew_operation(db, operation["id"], claim)
        if not _matching_plan_time(token, base_url, values, plan_id):
            create_plan_time(
                base_url,
                token,
                values["service_type_id"],
                plan_id,
                values["plan_date"],
                values["plan_time"],
                values["timezone_offset"],
            )
        _advance_operation(db, operation["id"], claim, "time_created")
        operation = _get_operation(db, operation["operation_key"])

    if operation.get("step") == "template_importing":
        raise PcoSyncError(
            "Planning Center template import has an uncertain result and requires manual resolution."
        )
    if _step_rank(operation.get("step")) < _step_rank("template_imported"):
        if values.get("template_id"):
            _advance_operation(db, operation["id"], claim, "template_importing")
            _renew_operation(db, operation["id"], claim)
            import_plan_template(
                base_url,
                token,
                values["service_type_id"],
                plan_id,
                values["template_id"],
            )
        _advance_operation(db, operation["id"], claim, "template_imported")

    _advance_operation(db, operation["id"], claim, "completed", status="completed")
    return _get_operation(db, operation["operation_key"])


def _ensure_operation(db, user_id, service_id, values):
    key = _operation_key(user_id, service_id, values)
    existing = _get_operation(db, key)
    if existing:
        return existing
    db.execute(
        """
        insert or ignore into pco_plan_operations (
          id, operation_key, user_id, service_id, mode, pco_service_type_id,
          pco_service_type_name, pco_plan_title, plan_date, plan_time,
          timezone_offset, template_id, series_title
        ) values (?, ?, ?, ?, 'create_new', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid.uuid4().hex,
            key,
            user_id,
            service_id,
            values["service_type_id"],
            values.get("service_type_name"),
            values["plan_title"],
            values["plan_date"],
            values["plan_time"],
            int(values["timezone_offset"]),
            values.get("template_id"),
            values.get("series_title"),
        ),
    )
    return _get_operation(db, key)


def _ensure_baseline(db, operation, claim, token, base_url, values):
    if operation.get("baseline_plan_ids_json") is not None:
        return operation
    _renew_operation(db, operation["id"], claim)
    plans = list_plans_by_title(
        base_url, token, values["service_type_id"], values["plan_title"]
    )
    baseline = sorted(str(row["id"]) for row in plans if row.get("id") is not None)
    db.execute(
        """
        update pco_plan_operations set baseline_plan_ids_json=?, updated_at=CURRENT_TIMESTAMP
        where id=? and claim_token=? and baseline_plan_ids_json is null
        """,
        (json.dumps(baseline, separators=(",", ":")), operation["id"], claim),
    )
    return _get_operation(db, operation["operation_key"])


def _reconcile_created_plan(operation, token, base_url, values):
    baseline = set(json.loads(operation.get("baseline_plan_ids_json") or "[]"))
    matches = [
        row
        for row in list_plans_by_title(
            base_url, token, values["service_type_id"], values["plan_title"]
        )
        if str(row.get("id")) not in baseline
        and _plan_matches_date(row, values["plan_date"])
    ]
    if len(matches) > 1:
        raise PcoSyncError(
            "Planning Center plan creation has an uncertain result: multiple new plans match."
        )
    return matches[0] if matches else None


def _plan_matches_date(plan, plan_date):
    sort_date = (plan.get("attributes") or {}).get("sort_date") or ""
    return not sort_date or str(sort_date).startswith(str(plan_date))


def _matching_plan_time(token, base_url, values, plan_id):
    expected, _ends = _build_plan_time_range(
        values["plan_date"], values["plan_time"], values["timezone_offset"]
    )
    matches = [
        row
        for row in list_plan_times(base_url, token, values["service_type_id"], plan_id)
        if (row.get("attributes") or {}).get("starts_at") == expected
    ]
    if len(matches) > 1:
        raise PcoSyncError("Multiple Planning Center plan times match this operation.")
    return bool(matches)


def _operation_key(user_id, service_id, values):
    stable = json.dumps(
        {"user_id": user_id, "service_id": service_id, **values},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _claim_operation(db, operation_id, lease_seconds):
    claim = uuid.uuid4().hex
    now = int(time.time())
    cursor = db.execute(
        """
        update pco_plan_operations set
          claim_token=?, claim_expires_at=?, status='running', updated_at=CURRENT_TIMESTAMP
        where id=? and (claim_token is null or coalesce(claim_expires_at, 0) <= ?)
        """,
        (claim, now + int(lease_seconds), operation_id, now),
    )
    return claim if cursor.rowcount == 1 else None


def _renew_operation(
    db, operation_id, claim, lease_seconds=PLAN_OPERATION_LEASE_SECONDS
):
    now = int(time.time())
    cursor = db.execute(
        """
        update pco_plan_operations set claim_expires_at=?, updated_at=CURRENT_TIMESTAMP
        where id=? and claim_token=? and claim_expires_at > ?
        """,
        (now + lease_seconds, operation_id, claim, now),
    )
    if cursor.rowcount != 1:
        raise PcoPlanOperationBusy("Planning Center plan setup lease was lost.")


def _advance_operation(
    db, operation_id, claim, step, *, plan_id=None, plan_title=None, status="running"
):
    cursor = db.execute(
        """
        update pco_plan_operations set
          step=?, status=?, pco_plan_id=coalesce(?, pco_plan_id),
          pco_plan_title=coalesce(?, pco_plan_title), error_category=null,
          updated_at=CURRENT_TIMESTAMP,
          completed_at=case when ?='completed' then CURRENT_TIMESTAMP else completed_at end
        where id=? and claim_token=?
        """,
        (step, status, plan_id, plan_title, status, operation_id, claim),
    )
    if cursor.rowcount != 1:
        raise PcoPlanOperationBusy("Planning Center plan setup lease was lost.")


def _mark_operation_retry(db, operation_id, claim, error):
    try:
        raise_if_retryable_pco_error(error)
    except RetryablePcoJobError as classified:
        status, category = "retry", classified.category
    else:
        try:
            raise_if_terminal_pco_auth(error)
        except TerminalPcoAuthError:
            status, category = "failed", "auth"
        else:
            try:
                raise_if_terminal_pco_error(error)
            except TerminalPcoJobError as terminal:
                status, category = "failed", terminal.category
            else:
                status, category = "retry", "internal"
    db.execute(
        """
        update pco_plan_operations set status=?, error_category=?,
          updated_at=CURRENT_TIMESTAMP
        where id=? and claim_token=?
        """,
        (status, category, operation_id, claim),
    )


def _release_operation(db, operation_id, claim):
    db.execute(
        """
        update pco_plan_operations set claim_token=null, claim_expires_at=null,
          updated_at=CURRENT_TIMESTAMP where id=? and claim_token=?
        """,
        (operation_id, claim),
    )


def _get_operation(db, key):
    row = db.execute(
        "select * from pco_plan_operations where operation_key=? limit 1", (key,)
    ).fetchone()
    return dict(row) if row else None


def _operation_result(operation):
    return (
        str(operation["pco_plan_id"]),
        operation.get("pco_plan_title"),
        operation["id"],
    )


def _step_rank(step):
    return {
        "pending": 0,
        "plan_created": 1,
        "time_created": 2,
        "template_importing": 3,
        "template_imported": 4,
        "completed": 5,
    }.get(step or "pending", 0)
