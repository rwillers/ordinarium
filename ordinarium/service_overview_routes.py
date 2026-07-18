from datetime import date

from flask import current_app, g, redirect, render_template, request, url_for

from .auth_session import login_required
from .db import get_database_gateway
from .error_pages import render_error
from .liturgical_calendar import resolve_observance, resolve_season
from .service_defaults import DEFAULT_RITE, OFFERTORY_DEFAULT_PREFIX
from .service_planning import build_plan_context
from .service_formatting import format_services
from .service_options import load_rite_options
from .feature_flags import FEATURE_PCO_SYNC, user_has_feature
from .service_copy import (
    create_service_from_copy,
    load_service_copy_source,
    overwrite_service_from_copy,
    service_copy_rite,
)
from .service_store import blank_service_payload, create_service, load_service_payload
from .pco_auth import get_valid_pco_connection
from .pco_sync_status import resolve_pco_sync_state
from .pco_store import get_service_pco_link
from .pco_sync import list_service_types
from .infrastructure import DatabaseStatement
from .user_settings import resolve_user_settings


def register_service_overview_routes(bp):
    @bp.route("/services")
    @login_required
    def services():
        db = get_database_gateway()
        rite_options = load_rite_options()
        user_settings = resolve_user_settings(g.user, rite_options)
        today = date.today().isoformat()
        current_services = db.fetch_all(
            "select id, title, season, service_date, rite, observance_handle, updated_at from services where user_id=? and service_date is not null and service_date >= ? order by service_date asc",
            (g.user["id"], today),
        )
        past_services = db.fetch_all(
            "select id, title, season, service_date, rite, observance_handle from services where user_id=? and service_date is not null and service_date < ? order by service_date desc",
            (g.user["id"], today),
        )
        copy_services = db.fetch_all(
            "select id, title, season, service_date, rite, observance_handle from services where user_id=? order by service_date desc",
            (g.user["id"],),
        )
        formatted_current_services = format_services(current_services)
        pco_enabled = user_has_feature(g.user, FEATURE_PCO_SYNC)
        pco_connection = None
        pco_service_types = []
        pco_links = {}
        if pco_enabled:
            try:
                pco_connection = get_valid_pco_connection(g.user["id"], db)
            except Exception:
                pco_connection = None
            if pco_connection:
                try:
                    pco_service_types = list_service_types(
                        current_app.config.get("PCO_API_BASE"),
                        pco_connection["access_token"],
                    )
                except Exception:
                    pco_service_types = []
            if formatted_current_services:
                current_ids = [row["id"] for row in formatted_current_services]
                placeholders = ",".join(["?"] * len(current_ids))
                rows = db.fetch_all(
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
                    current_ids,
                )
                pco_links = {row["service_id"]: dict(row) for row in rows}
            for service in formatted_current_services:
                if not pco_connection:
                    service["pco_status"] = {
                        "state": "disconnected",
                        "icon_state": "unlinked",
                        "label": "Not connected",
                    }
                    continue
                pco_link = pco_links.get(service["id"])
                if not pco_link:
                    service["pco_status"] = {
                        "state": "unlinked",
                        "icon_state": "unlinked",
                        "label": "Not linked",
                    }
                    continue
                sync_state = resolve_pco_sync_state(
                    service.get("updated_at"),
                    pco_link.get("last_synced_at"),
                    pco_link.get("last_sync_status"),
                )
                status_label = "Synced"
                status_icon = "synced"
                if sync_state == "failed":
                    status_label = "Last sync failed"
                    status_icon = "unsynced"
                elif sync_state == "unsynced":
                    status_label = "Unsynced changes"
                    status_icon = "unsynced"
                service["pco_status"] = {
                    "state": sync_state,
                    "icon_state": status_icon,
                    "label": status_label,
                }

        return render_template(
            "services.html",
            current_services=formatted_current_services,
            past_services=format_services(past_services),
            copy_services=format_services(copy_services),
            default_rite=user_settings["default_rite"],
            default_service_time=user_settings["default_service_time"],
            rite_options=rite_options,
            pco_enabled=pco_enabled,
            pco_connected=bool(pco_connection) if pco_enabled else False,
            pco_service_types=pco_service_types,
            pco_links=pco_links,
        )

    def _create_service_from_request():
        db = get_database_gateway()
        rite_options = load_rite_options()
        user_settings = resolve_user_settings(g.user, rite_options)
        rite = user_settings["default_rite"]
        if request.method != "POST":
            return redirect(url_for("main.services"))

        def normalize_value(value):
            if value is None:
                return None
            value = value.strip()
            return value or None

        mode = request.form.get("mode", "defaults")
        add_mode = request.form.get("add_mode", "single")
        rite = request.form.get("rite") or user_settings["default_rite"]

        source_copy = None

        if mode == "copy":
            raw_source_id = request.form.get("from_service_id")
            try:
                source_id = int(raw_source_id)
            except (TypeError, ValueError):
                source_id = None
            if not source_id:
                return render_error("Select a service to copy.", 400)
            source_copy = load_service_copy_source(db, source_id, g.user["id"])
            if not source_copy:
                return render_error("Service not found.", 404)
            if service_copy_rite(source_copy) != rite:
                return render_error("Service rite does not match.", 400)

        def build_base_payload(raw_date, handle):
            if not raw_date:
                return None, "Service date is required."
            try:
                parsed_date = date.fromisoformat(raw_date)
            except ValueError:
                return None, "Invalid service date."
            observance = resolve_observance(parsed_date, handle)
            title = None
            observance_handle = None
            if observance:
                observance_handle = observance.handle
                title = observance.name or observance.alternative_name or ""
            return (
                {
                    "service_date": raw_date,
                    "season": resolve_season(parsed_date),
                    "observance_handle": observance_handle,
                    "title": title or None,
                },
                None,
            )

        def create_service_from_payload(base_payload):
            if mode == "copy":
                return create_service_from_copy(
                    db, g.user["id"], source_copy, base_payload
                )

            payload = blank_service_payload(g.user["id"], rite)
            payload.update(base_payload)
            return create_service(db, payload)

        if add_mode == "multiple":
            raw_count = normalize_value(request.form.get("multi_count"))
            try:
                count = int(raw_count)
            except (TypeError, ValueError):
                count = 0
            if count < 2 or count > 10:
                return render_error("Select how many services to add (2-10).", 400)
            raw_dates = request.form.getlist("service_dates")
            if len(raw_dates) != count:
                return render_error("Provide a service date for each service.", 400)
            raw_handles = request.form.getlist("observance_handles")
            for index, raw_date in enumerate(raw_dates):
                normalized_date = normalize_value(raw_date)
                handle = (
                    normalize_value(raw_handles[index])
                    if index < len(raw_handles)
                    else None
                )
                base_payload, error = build_base_payload(normalized_date, handle)
                if error:
                    message = (
                        "Service dates are required for each service."
                        if error == "Service date is required."
                        else error
                    )
                    return render_error(message, 400)
                create_service_from_payload(base_payload)
            return redirect(url_for("main.services"))

        raw_date = normalize_value(request.form.get("service_date"))
        base_payload, error = build_base_payload(
            raw_date, normalize_value(request.form.get("observance_handle"))
        )
        if error:
            return render_error(error, 400)
        new_service_id = create_service_from_payload(base_payload)
        return redirect(url_for("main.service", service_id=new_service_id))

    @bp.route("/services", methods=["POST"])
    @login_required
    def services_create():
        return _create_service_from_request()

    @bp.route("/services/new", methods=["GET", "POST"])
    @login_required
    def services_new():
        return _create_service_from_request()

    @bp.route("/service/<int:service_id>")
    @login_required
    def service(service_id, rite=DEFAULT_RITE):
        db = get_database_gateway()
        existing_owner = db.fetch_one(
            "select user_id from services where id=? limit 1", (service_id,)
        )
        if not existing_owner or existing_owner["user_id"] != g.user["id"]:
            return render_error("Service not found.", 404)
        context = build_plan_context(
            service_id, rite, g.user["id"], OFFERTORY_DEFAULT_PREFIX
        )
        today = date.today().isoformat()
        copy_target_rows = db.fetch_all(
            """
            select id, title, season, service_date, rite, observance_handle
            from services
            where user_id=?
              and id<>?
              and service_date is not null
              and service_date >= ?
              and coalesce(rite, ?) = ?
            order by service_date asc
            """,
            (
                g.user["id"],
                service_id,
                today,
                DEFAULT_RITE,
                context["service"]["rite"] or DEFAULT_RITE,
            ),
        )
        pco_enabled = user_has_feature(g.user, FEATURE_PCO_SYNC)
        pco_connection = None
        pco_service_types = []
        pco_link = get_service_pco_link(service_id, db=db)
        if pco_enabled:
            try:
                pco_connection = get_valid_pco_connection(g.user["id"], db)
            except Exception:
                pco_connection = None
            if pco_connection:
                try:
                    pco_service_types = list_service_types(
                        current_app.config.get("PCO_API_BASE"),
                        pco_connection["access_token"],
                    )
                except Exception:
                    pco_service_types = []
        pco_sync_state = None
        pco_sync_at = None
        if pco_link:
            pco_sync_at = pco_link["last_synced_at"]
            service_updated_at = context.get("service", {}).get("updated_at")
            pco_sync_state = resolve_pco_sync_state(
                service_updated_at,
                pco_link["last_synced_at"],
                pco_link["last_sync_status"],
            )
        user_settings = resolve_user_settings(g.user)
        context.update(
            {
                "pco_connected": bool(pco_connection) if pco_enabled else False,
                "pco_link": pco_link,
                "pco_service_types": pco_service_types,
                "pco_sync_state": pco_sync_state,
                "pco_sync_at": pco_sync_at,
                "default_service_time": user_settings["default_service_time"],
                "copy_target_services": format_services(copy_target_rows),
            }
        )
        return render_template("service.html", **context)

    @bp.route("/service/<int:service_id>/copy-elements", methods=["POST"])
    @login_required
    def service_copy_elements(service_id):
        raw_ids = request.form.getlist("service_ids")
        target_ids = []
        for raw_id in raw_ids:
            try:
                target_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if target_id not in target_ids:
                target_ids.append(target_id)

        if not target_ids:
            return render_error("Select at least one service to copy to.", 400)
        if service_id in target_ids:
            return render_error("Cannot copy a service to itself.", 400)

        db = get_database_gateway()
        source_copy = load_service_copy_source(db, service_id, g.user["id"])
        if not source_copy:
            return render_error("Service not found.", 404)

        placeholders = ",".join(["?"] * len(target_ids))
        target_rows = db.fetch_all(
            f"""
            select id, rite, service_date
            from services
            where user_id=? and id in ({placeholders})
            """,
            [g.user["id"], *target_ids],
        )
        if len(target_rows) != len(target_ids):
            return render_error("Service not found.", 404)

        today = date.today().isoformat()
        source_rite = service_copy_rite(source_copy)
        for row in target_rows:
            target_rite = row["rite"] or DEFAULT_RITE
            if target_rite != source_rite:
                return render_error("Service rite does not match.", 400)
            if not row["service_date"] or row["service_date"] < today:
                return render_error("Select future services only.", 400)

        for target_id in target_ids:
            target_payload = load_service_payload(db, target_id, g.user["id"])
            if not target_payload:
                return render_error("Service not found.", 404)
            overwrite_service_from_copy(
                db, g.user["id"], source_copy, target_id, target_payload
            )
        return redirect(url_for("main.service", service_id=service_id))

    @bp.route("/service/<int:service_id>/delete", methods=["POST"])
    @login_required
    def service_delete(service_id):
        db = get_database_gateway()
        db.batch(
            [
                DatabaseStatement(
                    "delete from service_custom_elements where service_id=? and user_id=?",
                    (service_id, g.user["id"]),
                ),
                DatabaseStatement(
                    "delete from service_shares where service_id=?",
                    (service_id,),
                ),
                DatabaseStatement(
                    "delete from services where id=? and user_id=?",
                    (service_id, g.user["id"]),
                ),
            ]
        )
        return redirect(url_for("main.services"))

    @bp.route("/services/bulk-delete", methods=["POST"])
    @login_required
    def services_bulk_delete():
        raw_ids = request.form.getlist("service_ids")
        service_ids = []
        for raw_id in raw_ids:
            try:
                service_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        if not service_ids:
            return redirect(url_for("main.services"))

        placeholders = ",".join(["?"] * len(service_ids))
        params = [g.user["id"], *service_ids]
        db = get_database_gateway()
        db.batch(
            [
                DatabaseStatement(
                    f"delete from service_custom_elements where user_id=? and service_id in ({placeholders})",
                    params,
                ),
                DatabaseStatement(
                    f"delete from service_shares where service_id in ({placeholders})",
                    service_ids,
                ),
                DatabaseStatement(
                    f"delete from services where user_id=? and id in ({placeholders})",
                    params,
                ),
            ]
        )
        return redirect(url_for("main.services"))
