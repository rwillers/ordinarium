from datetime import datetime

from flask import current_app, flash, g, jsonify, redirect, request, url_for

from .auth_session import login_required
from .db import get_db
from .error_pages import render_error
from .feature_flags import FEATURE_PCO_SYNC, user_has_feature
from .pco_client import PcoApiError, PcoAuthError
from .pco_auth import get_valid_pco_connection
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
    list_plans_for_date,
    sync_service_plan,
)


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
