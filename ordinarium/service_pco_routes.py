import threading
from datetime import date, datetime

from flask import current_app, flash, g, jsonify, redirect, request, url_for

from .auth_session import login_required
from .db import close_db, get_db
from .error_pages import render_error
from .feature_flags import FEATURE_PCO_SYNC, user_has_feature
from .pco_auth import get_valid_pco_connection
from .pco_batch_jobs import (
    BATCH_JOB_FAILED,
    BATCH_JOB_SUCCEEDED,
    complete_pco_batch_sync_job,
    create_pco_batch_sync_job,
    fail_pco_batch_sync_job,
    get_pco_batch_sync_job,
    mark_pco_batch_sync_job_running,
    update_pco_batch_sync_job_results,
)
from .pco_client import PcoApiError, PcoAuthError
from .pco_store import (
    clear_service_pco_link,
    update_service_pco_sync_status,
    upsert_service_pco_link,
)
from .pco_sync import (
    PcoSyncError,
    create_plan,
    create_plan_time,
    fetch_plan,
    import_plan_template,
    list_plans_for_date,
    list_plan_templates,
    sync_service_plan,
)

BATCH_SYNC_LIMIT = 25
BATCH_SYNC_MODES = {"sync_linked", "link_existing", "create_new", "skip"}


def _to_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _parse_service_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_pco_template(template):
    attributes = template.get("attributes") or {}
    return {
        "id": template.get("id"),
        "name": attributes.get("name") or "Untitled template",
        "item_count": attributes.get("item_count") or 0,
        "team_count": attributes.get("team_count") or 0,
        "note_count": attributes.get("note_count") or 0,
    }


def _load_batch_services(db, user_id, service_ids):
    if not service_ids:
        return {}
    placeholders = ",".join(["?"] * len(service_ids))
    today = date.today().isoformat()
    rows = db.execute(
        f"""
        select id, title, season, service_date
        from services
        where user_id=?
          and id in ({placeholders})
          and service_date is not null
          and service_date >= ?
        """,
        [user_id, *service_ids, today],
    ).fetchall()
    return {row["id"]: dict(row) for row in rows}


def _load_batch_links(db, service_ids):
    if not service_ids:
        return {}
    placeholders = ",".join(["?"] * len(service_ids))
    rows = db.execute(
        f"""
        select
          service_id,
          pco_service_type_id,
          pco_service_type_name,
          pco_plan_id,
          pco_plan_title,
          last_synced_at,
          last_sync_status,
          last_sync_error
        from service_pco_links
        where service_id in ({placeholders})
        """,
        service_ids,
    ).fetchall()
    return {row["service_id"]: dict(row) for row in rows}


def _run_service_sync(
    service_id,
    user_id,
    access_token,
    base_url,
    service_type_id,
    plan_id,
    db,
):
    try:
        result = sync_service_plan(
            service_id,
            user_id,
            access_token,
            base_url,
            service_type_id,
            plan_id,
        )
    except Exception as exc:
        failed_at = datetime.utcnow().isoformat()
        update_service_pco_sync_status(
            service_id,
            "failed",
            error=str(exc),
            synced_at=failed_at,
            db=db,
        )
        return False, {"synced_at": failed_at, "error": str(exc)}
    synced_at = result.get("synced_at")
    update_service_pco_sync_status(
        service_id,
        "success",
        error=None,
        synced_at=synced_at,
        db=db,
    )
    return True, {"synced_at": synced_at, "item_count": result.get("item_count", 0)}


def _summarize_batch_results(results):
    summary = {"total": len(results), "success": 0, "failed": 0, "skipped": 0}
    for row in results:
        status = row.get("status")
        if status == "success":
            summary["success"] += 1
        elif status == "failed":
            summary["failed"] += 1
        elif status == "skipped":
            summary["skipped"] += 1
    return summary


def _validate_batch_sync_payload(payload):
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        return "Select at least one upcoming service for PCO sync."
    if len(raw_rows) > BATCH_SYNC_LIMIT:
        return f"Select up to {BATCH_SYNC_LIMIT} services at a time."
    tz_offset = _to_text(payload.get("pco_plan_tz_offset"))
    if not tz_offset:
        return "Timezone offset is required."
    try:
        int(tz_offset)
    except ValueError:
        return "Timezone offset must be an integer."
    return None


def _ordered_batch_results(raw_rows, results_by_index):
    ordered_results = []
    for index in range(len(raw_rows)):
        row_result = results_by_index.get(index)
        if not row_result:
            row_result = {
                "service_id": None,
                "mode": "",
                "status": "pending",
                "error": "",
            }
        ordered_results.append(row_result)
    return ordered_results


def _execute_pco_batch_sync(
    user_id, access_token, base_url, payload, db, on_progress=None
):
    raw_rows = payload.get("rows") or []
    default_plan_time = _to_text(payload.get("pco_plan_time")) or "10:00"
    tz_offset = _to_text(payload.get("pco_plan_tz_offset"))
    prepared = []
    results_by_index = {}

    def store_result(index, result):
        results_by_index[index] = result
        if on_progress:
            results = _ordered_batch_results(raw_rows, results_by_index)
            on_progress(results, _summarize_batch_results(results))

    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, dict):
            store_result(
                index,
                {
                    "service_id": None,
                    "mode": "",
                    "status": "failed",
                    "error": "Invalid row payload.",
                },
            )
            continue
        service_id = _parse_service_id(raw.get("service_id"))
        mode = _to_text(raw.get("mode"))
        prepared_row = {
            "index": index,
            "service_id": service_id,
            "mode": mode,
            "pco_service_type_id": _to_text(raw.get("pco_service_type_id")),
            "pco_service_type_name": _to_text(raw.get("pco_service_type_name")),
            "pco_plan_id": _to_text(raw.get("pco_plan_id")),
            "pco_plan_template_id": _to_text(raw.get("pco_plan_template_id")),
        }
        if not service_id:
            store_result(
                index,
                {
                    "service_id": None,
                    "mode": mode,
                    "status": "failed",
                    "error": "Service ID is required.",
                },
            )
            continue
        if mode not in BATCH_SYNC_MODES:
            store_result(
                index,
                {
                    "service_id": service_id,
                    "mode": mode,
                    "status": "failed",
                    "error": "Invalid batch mode.",
                },
            )
            continue
        prepared.append(prepared_row)

    service_ids = []
    seen_ids = set()
    for row in prepared:
        service_id = row["service_id"]
        if service_id in seen_ids:
            continue
        seen_ids.add(service_id)
        service_ids.append(service_id)

    services_by_id = _load_batch_services(db, user_id, service_ids)
    links_by_id = _load_batch_links(db, service_ids)
    duplicate_indexes = _duplicate_batch_target_indexes(
        prepared, results_by_index, services_by_id, links_by_id
    )

    for row in prepared:
        index = row["index"]
        if index in results_by_index:
            continue
        result = _execute_pco_batch_row(
            row,
            user_id,
            access_token,
            base_url,
            default_plan_time,
            tz_offset,
            db,
            services_by_id,
            links_by_id,
            duplicate_indexes,
        )
        db.commit()
        store_result(index, result)

    ordered_results = []
    for index in range(len(raw_rows)):
        row_result = results_by_index.get(index)
        if not row_result:
            row_result = {
                "service_id": None,
                "mode": "",
                "status": "failed",
                "error": "Unable to process row.",
            }
        ordered_results.append(row_result)
    summary = _summarize_batch_results(ordered_results)
    return {"ok": True, "summary": summary, "results": ordered_results}


def _duplicate_batch_target_indexes(
    prepared, results_by_index, services_by_id, links_by_id
):
    target_map = {}
    duplicate_indexes = set()
    for row in prepared:
        index = row["index"]
        if index in results_by_index:
            continue
        mode = row["mode"]
        if mode == "skip":
            continue
        service = services_by_id.get(row["service_id"])
        if not service:
            continue
        target = None
        if mode == "sync_linked":
            link = links_by_id.get(row["service_id"])
            if link:
                target = (link["pco_service_type_id"], link["pco_plan_id"])
        elif mode == "link_existing":
            service_type_id = row["pco_service_type_id"]
            plan_id = row["pco_plan_id"]
            if service_type_id and plan_id:
                target = (service_type_id, plan_id)
        if not target:
            continue
        target_map.setdefault(target, []).append(index)
    for indexes in target_map.values():
        if len(indexes) > 1:
            duplicate_indexes.update(indexes)
    return duplicate_indexes


def _execute_pco_batch_row(
    row,
    user_id,
    access_token,
    base_url,
    default_plan_time,
    tz_offset,
    db,
    services_by_id,
    links_by_id,
    duplicate_indexes,
):
    service_id = row["service_id"]
    mode = row["mode"]
    service = services_by_id.get(service_id)
    service_title = ""
    service_date = ""
    if service:
        service_title = (
            _to_text(service.get("title")) or f"Service {service['service_date']}"
        )
        service_date = _to_text(service.get("service_date"))
    result = {
        "service_id": service_id,
        "service_title": service_title,
        "service_date": service_date,
        "mode": mode,
    }
    if mode == "skip":
        result["status"] = "skipped"
        return result
    if not service:
        result["status"] = "failed"
        result["error"] = "Service not found or is not upcoming."
        return result
    if row["index"] in duplicate_indexes:
        result["status"] = "failed"
        result["error"] = (
            "Multiple rows target the same Planning Center plan in this batch."
        )
        return result
    if mode == "sync_linked":
        return _execute_pco_linked_batch_row(
            result, service_id, user_id, access_token, base_url, db, links_by_id
        )

    service_type_id = row["pco_service_type_id"]
    if not service_type_id:
        result["status"] = "failed"
        result["error"] = "PCO service type is required."
        return result
    service_type_name = row["pco_service_type_name"] or None
    plan_id = None
    plan_title = None
    if mode == "link_existing":
        plan_id, plan_title, error = _resolve_existing_pco_plan(
            base_url, access_token, service_type_id, row["pco_plan_id"]
        )
        if error:
            result["status"] = "failed"
            result["error"] = error
            return result
    if mode == "create_new":
        plan_id, plan_title, error = _create_pco_plan_for_batch_row(
            base_url,
            access_token,
            service_type_id,
            service_title,
            service,
            default_plan_time,
            tz_offset,
            row["pco_plan_template_id"],
        )
        if error:
            result["status"] = "failed"
            result["error"] = error
            return result
    upsert_service_pco_link(
        service_id,
        service_type_id,
        plan_id,
        pco_service_type_name=service_type_name,
        pco_plan_title=plan_title,
        db=db,
    )
    links_by_id[service_id] = {
        "service_id": service_id,
        "pco_service_type_id": service_type_id,
        "pco_service_type_name": service_type_name,
        "pco_plan_id": plan_id,
        "pco_plan_title": plan_title,
    }
    ok, sync_data = _run_service_sync(
        service_id,
        user_id,
        access_token,
        base_url,
        service_type_id,
        plan_id,
        db,
    )
    result.update(
        {
            "pco_service_type_id": service_type_id,
            "pco_service_type_name": service_type_name,
            "pco_plan_id": plan_id,
            "pco_plan_title": plan_title,
            "synced_at": sync_data.get("synced_at"),
        }
    )
    if ok:
        result["status"] = "success"
        return result
    result["status"] = "failed"
    result["error"] = sync_data.get("error") or "PCO sync failed."
    return result


def _execute_pco_linked_batch_row(
    result, service_id, user_id, access_token, base_url, db, links_by_id
):
    link = links_by_id.get(service_id)
    if not link:
        result["status"] = "failed"
        result["error"] = "Planning Center plan not linked."
        return result
    ok, sync_data = _run_service_sync(
        service_id,
        user_id,
        access_token,
        base_url,
        link["pco_service_type_id"],
        link["pco_plan_id"],
        db,
    )
    result.update(
        {
            "pco_service_type_id": link["pco_service_type_id"],
            "pco_service_type_name": link.get("pco_service_type_name"),
            "pco_plan_id": link["pco_plan_id"],
            "pco_plan_title": link.get("pco_plan_title"),
            "synced_at": sync_data.get("synced_at"),
        }
    )
    if ok:
        result["status"] = "success"
        return result
    result["status"] = "failed"
    result["error"] = sync_data.get("error") or "PCO sync failed."
    return result


def _resolve_existing_pco_plan(base_url, access_token, service_type_id, plan_id):
    if not plan_id:
        return None, None, "PCO plan is required for link existing mode."
    try:
        plan = fetch_plan(base_url, access_token, service_type_id, plan_id)
    except PcoApiError as exc:
        return None, None, str(exc)
    plan_data = plan.get("data") if plan else None
    if not plan_data:
        return None, None, "PCO plan not found."
    return plan_id, (plan_data.get("attributes") or {}).get("title"), None


def _create_pco_plan_for_batch_row(
    base_url,
    access_token,
    service_type_id,
    service_title,
    service,
    default_plan_time,
    tz_offset,
    plan_template_id=None,
):
    create_title = service_title or f"Service {service['service_date']}"
    create_date = service["service_date"]
    series_title = _to_text(service.get("season")) or None
    try:
        created = create_plan(
            base_url,
            access_token,
            service_type_id,
            create_title,
            create_date,
            series_title,
        )
    except PcoApiError as exc:
        return None, None, str(exc)
    plan_data = created.get("data") if created else None
    if not plan_data:
        return None, None, "PCO plan creation failed."
    plan_id = _to_text(plan_data.get("id"))
    plan_title = (plan_data.get("attributes") or {}).get("title")
    if not plan_id:
        return None, None, "PCO plan creation failed."
    try:
        create_plan_time(
            base_url,
            access_token,
            service_type_id,
            plan_id,
            create_date,
            default_plan_time,
            tz_offset,
        )
    except (PcoApiError, PcoSyncError) as exc:
        return None, None, str(exc)
    if plan_template_id:
        try:
            import_plan_template(
                base_url,
                access_token,
                service_type_id,
                plan_id,
                plan_template_id,
            )
        except PcoApiError as exc:
            return None, None, str(exc)
    return plan_id, plan_title, None


def _start_pco_batch_sync_worker(app, job_id, user_id):
    thread = threading.Thread(
        target=_run_pco_batch_sync_worker,
        args=(app, job_id, user_id),
        daemon=True,
    )
    thread.start()


def _run_pco_batch_sync_worker(app, job_id, user_id):
    with app.app_context():
        db = get_db()
        try:
            job = get_pco_batch_sync_job(job_id, user_id, db=db)
            if not job:
                return
            mark_pco_batch_sync_job_running(job_id, db=db)
            db.commit()
            connection = get_valid_pco_connection(user_id, db)
            if not connection:
                raise PcoAuthError("Planning Center is not connected.")

            def on_progress(results, summary):
                update_pco_batch_sync_job_results(job_id, results, summary, db=db)
                db.commit()

            payload = _execute_pco_batch_sync(
                user_id,
                connection["access_token"],
                app.config.get("PCO_API_BASE"),
                job["request_payload"],
                db,
                on_progress=on_progress,
            )
            complete_pco_batch_sync_job(
                job_id,
                payload["results"],
                payload["summary"],
                db=db,
            )
            db.commit()
        except Exception as exc:
            fail_pco_batch_sync_job(job_id, exc, db=db)
            db.commit()
        finally:
            close_db(None)


def register_service_pco_routes(bp):
    def _pco_feature_enabled():
        return user_has_feature(g.user, FEATURE_PCO_SYNC)

    @bp.route("/service/<int:service_id>/pco/link", methods=["POST"])
    @login_required
    def service_pco_link(service_id):
        if not _pco_feature_enabled():
            return render_error("Not found.", 404)
        db = get_db()
        owner = db.execute(
            "select id from services where id=? and user_id=? limit 1",
            (service_id, g.user["id"]),
        ).fetchone()
        if not owner:
            return render_error("Service not found.", 404)
        try:
            connection = get_valid_pco_connection(g.user["id"], db)
        except PcoAuthError as exc:
            return render_error(str(exc), 400)
        if not connection:
            return render_error("Planning Center is not connected.", 400)
        mode = request.form.get("mode", "existing")
        service_type_id = request.form.get("pco_service_type_id")
        if not service_type_id:
            return render_error("PCO service type is required.", 400)
        base_url = current_app.config.get("PCO_API_BASE")
        if mode == "create":
            plan_title = request.form.get("pco_plan_title")
            plan_date = request.form.get("pco_plan_date")
            plan_time = request.form.get("pco_plan_time")
            tz_offset = request.form.get("pco_plan_tz_offset")
            series_title = request.form.get("pco_series_title")
            plan_template_id = _to_text(request.form.get("pco_plan_template_id"))
            if not plan_title:
                return render_error("Plan title is required.", 400)
            if not plan_date:
                return render_error("Plan date is required.", 400)
            if not plan_time:
                return render_error("Plan time is required.", 400)
            try:
                created = create_plan(
                    base_url,
                    connection["access_token"],
                    service_type_id,
                    plan_title,
                    plan_date,
                    series_title,
                )
            except PcoApiError as exc:
                return render_error(str(exc), 400)
            plan_data = created.get("data") if created else None
            if not plan_data:
                return render_error("PCO plan creation failed.", 400)
            plan_id = plan_data.get("id")
            plan_title = (plan_data.get("attributes") or {}).get("title")
            service_type_name = request.form.get("pco_service_type_name")
            try:
                create_plan_time(
                    base_url,
                    connection["access_token"],
                    service_type_id,
                    plan_id,
                    plan_date,
                    plan_time,
                    tz_offset,
                )
            except (PcoApiError, PcoSyncError) as exc:
                return render_error(str(exc), 400)
            if plan_template_id:
                try:
                    import_plan_template(
                        base_url,
                        connection["access_token"],
                        service_type_id,
                        plan_id,
                        plan_template_id,
                    )
                except PcoApiError as exc:
                    return render_error(str(exc), 400)
        else:
            plan_id = request.form.get("pco_plan_id")
            if not plan_id:
                return render_error("PCO plan ID is required.", 400)
            try:
                plan = fetch_plan(
                    base_url,
                    connection["access_token"],
                    service_type_id,
                    plan_id,
                )
            except PcoApiError as exc:
                return render_error(str(exc), 400)
            plan_data = plan.get("data") if plan else None
            if not plan_data:
                return render_error("PCO plan not found.", 404)
            plan_title = (plan_data.get("attributes") or {}).get("title")
            service_type_name = request.form.get("pco_service_type_name")
        upsert_service_pco_link(
            service_id,
            service_type_id,
            plan_id,
            pco_service_type_name=service_type_name,
            pco_plan_title=plan_title,
            db=db,
        )
        db.commit()
        flash("Planning Center plan linked.", "success")
        return redirect(url_for("main.service", service_id=service_id))

    @bp.route("/service/<int:service_id>/pco/unlink", methods=["POST"])
    @login_required
    def service_pco_unlink(service_id):
        if not _pco_feature_enabled():
            return render_error("Not found.", 404)
        db = get_db()
        owner = db.execute(
            "select id from services where id=? and user_id=? limit 1",
            (service_id, g.user["id"]),
        ).fetchone()
        if not owner:
            return render_error("Service not found.", 404)
        clear_service_pco_link(service_id, db=db)
        db.commit()
        flash("Planning Center link removed.", "success")
        return redirect(url_for("main.service", service_id=service_id))

    @bp.route("/service/<int:service_id>/pco/plans")
    @login_required
    def service_pco_plans(service_id):
        if not _pco_feature_enabled():
            return jsonify({"ok": False, "error": "Not found."}), 404
        db = get_db()
        service_row = db.execute(
            "select id, service_date from services where id=? and user_id=? limit 1",
            (service_id, g.user["id"]),
        ).fetchone()
        if not service_row:
            return jsonify({"ok": False, "error": "Service not found."}), 404
        if not service_row["service_date"]:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Service date is required to load plans.",
                    }
                ),
                400,
            )
        service_type_id = request.args.get("service_type_id")
        if not service_type_id:
            return (
                jsonify({"ok": False, "error": "Service type is required."}),
                400,
            )
        try:
            connection = get_valid_pco_connection(g.user["id"], db)
        except PcoAuthError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not connection:
            return (
                jsonify({"ok": False, "error": "Planning Center not connected."}),
                400,
            )
        try:
            plans = list_plans_for_date(
                current_app.config.get("PCO_API_BASE"),
                connection["access_token"],
                service_type_id,
                service_row["service_date"],
            )
        except PcoApiError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "plans": plans})

    @bp.route("/service/<int:service_id>/pco/templates")
    @login_required
    def service_pco_templates(service_id):
        if not _pco_feature_enabled():
            return jsonify({"ok": False, "error": "Not found."}), 404
        db = get_db()
        service_row = db.execute(
            "select id from services where id=? and user_id=? limit 1",
            (service_id, g.user["id"]),
        ).fetchone()
        if not service_row:
            return jsonify({"ok": False, "error": "Service not found."}), 404
        service_type_id = request.args.get("service_type_id")
        if not service_type_id:
            return (
                jsonify({"ok": False, "error": "Service type is required."}),
                400,
            )
        try:
            connection = get_valid_pco_connection(g.user["id"], db)
        except PcoAuthError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not connection:
            return (
                jsonify({"ok": False, "error": "Planning Center not connected."}),
                400,
            )
        try:
            templates = list_plan_templates(
                current_app.config.get("PCO_API_BASE"),
                connection["access_token"],
                service_type_id,
            )
        except PcoApiError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(
            {"ok": True, "templates": [_format_pco_template(row) for row in templates]}
        )

    @bp.route("/service/<int:service_id>/pco/sync", methods=["POST"])
    @login_required
    def service_pco_sync(service_id):
        wants_json = "application/json" in request.headers.get("Accept", "")
        if not _pco_feature_enabled():
            return render_error("Not found.", 404)
        db = get_db()
        owner = db.execute(
            "select id from services where id=? and user_id=? limit 1",
            (service_id, g.user["id"]),
        ).fetchone()
        if not owner:
            return render_error("Service not found.", 404)
        try:
            connection = get_valid_pco_connection(g.user["id"], db)
        except PcoAuthError as exc:
            if wants_json:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "sync_status": "failed",
                            "error": str(exc),
                        }
                    ),
                    400,
                )
            return render_error(str(exc), 400)
        if not connection:
            if wants_json:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "sync_status": "failed",
                            "error": "Planning Center is not connected.",
                        }
                    ),
                    400,
                )
            return render_error("Planning Center is not connected.", 400)
        link = db.execute(
            "select * from service_pco_links where service_id=? limit 1",
            (service_id,),
        ).fetchone()
        if not link:
            if wants_json:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "sync_status": "failed",
                            "error": "Planning Center plan not linked.",
                        }
                    ),
                    400,
                )
            return render_error("Planning Center plan not linked.", 400)
        try:
            result = sync_service_plan(
                service_id,
                g.user["id"],
                connection["access_token"],
                current_app.config.get("PCO_API_BASE"),
                link["pco_service_type_id"],
                link["pco_plan_id"],
            )
        except PcoAuthError as exc:
            failed_at = datetime.utcnow().isoformat()
            update_service_pco_sync_status(
                service_id, "failed", error=str(exc), synced_at=failed_at, db=db
            )
            db.commit()
            if wants_json:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "sync_status": "failed",
                            "synced_at": failed_at,
                            "error": str(exc),
                        }
                    ),
                    400,
                )
            return render_error("PCO authorization failed.", 400)
        except Exception as exc:
            failed_at = datetime.utcnow().isoformat()
            update_service_pco_sync_status(
                service_id, "failed", error=str(exc), synced_at=failed_at, db=db
            )
            db.commit()
            if wants_json:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "sync_status": "failed",
                            "synced_at": failed_at,
                            "error": str(exc),
                        }
                    ),
                    400,
                )
            return render_error("PCO sync failed.", 400)
        update_service_pco_sync_status(
            service_id, "success", error=None, synced_at=result.get("synced_at"), db=db
        )
        db.commit()
        if wants_json:
            return jsonify(
                {
                    "ok": True,
                    "sync_status": "success",
                    "synced_at": result.get("synced_at"),
                }
            )
        flash("Planning Center sync complete.", "success")
        return redirect(url_for("main.service", service_id=service_id))

    @bp.route("/services/pco/batch-sync", methods=["POST"])
    @login_required
    def services_pco_batch_sync():
        if not _pco_feature_enabled():
            return jsonify({"ok": False, "error": "Not found."}), 404
        db = get_db()
        try:
            connection = get_valid_pco_connection(g.user["id"], db)
        except PcoAuthError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not connection:
            return (
                jsonify({"ok": False, "error": "Planning Center is not connected."}),
                400,
            )
        payload = request.get_json(silent=True) or {}
        error = _validate_batch_sync_payload(payload)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        job_id = create_pco_batch_sync_job(g.user["id"], payload, db=db)
        db.commit()
        _start_pco_batch_sync_worker(
            current_app._get_current_object(), job_id, g.user["id"]
        )
        return (
            jsonify(
                {
                    "ok": True,
                    "job_id": job_id,
                    "status": "queued",
                    "status_url": url_for(
                        "main.services_pco_batch_sync_status", job_id=job_id
                    ),
                    "poll_after_ms": 1000,
                }
            ),
            202,
        )

    @bp.route("/services/pco/batch-sync/<job_id>")
    @login_required
    def services_pco_batch_sync_status(job_id):
        if not _pco_feature_enabled():
            return jsonify({"ok": False, "error": "Not found."}), 404
        job = get_pco_batch_sync_job(job_id, g.user["id"], db=get_db())
        if not job:
            return jsonify({"ok": False, "error": "Batch sync job not found."}), 404
        return jsonify(
            {
                "ok": job["status"] in {BATCH_JOB_SUCCEEDED, BATCH_JOB_FAILED},
                "job_id": job["id"],
                "status": job["status"],
                "summary": job["summary"],
                "results": job["results"],
                "error": job["error"],
                "created_at": job["created_at"],
                "updated_at": job["updated_at"],
                "completed_at": job["completed_at"],
                "poll_after_ms": 1000,
            }
        )
