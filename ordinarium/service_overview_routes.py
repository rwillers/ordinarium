import json
from datetime import date

from flask import current_app, g, redirect, render_template, request, url_for

from .auth_session import login_required
from .db import get_db
from .error_pages import render_error
from .service_defaults import DEFAULT_RITE, OFFERTORY_DEFAULT_PREFIX
from .service_planning import build_plan_context, parse_plan_tokens, _parse_json_object
from .service_formatting import format_services
from .service_options import load_rite_options
from .feature_flags import FEATURE_PCO_SYNC, user_has_feature
from .service_store import blank_service_payload, create_service, update_service_columns
from .pco_auth import get_valid_pco_connection
from .pco_store import get_service_pco_link
from .pco_sync import list_service_types


def register_service_overview_routes(bp):
    @bp.route("/services")
    @login_required
    def services():
        db = get_db()
        today = date.today().isoformat()
        current_services = db.execute(
            "select id, title, service_date, rite, observance_handle from services where user_id=? and service_date is not null and service_date >= ? order by service_date asc",
            (g.user["id"], today),
        ).fetchall()
        past_services = db.execute(
            "select id, title, service_date, rite, observance_handle from services where user_id=? and service_date is not null and service_date < ? order by service_date desc",
            (g.user["id"], today),
        ).fetchall()
        copy_services = db.execute(
            "select id, title, service_date, rite, observance_handle from services where user_id=? order by service_date desc",
            (g.user["id"],),
        ).fetchall()

        return render_template(
            "services.html",
            current_services=format_services(current_services),
            past_services=format_services(past_services),
            copy_services=format_services(copy_services),
            default_rite=DEFAULT_RITE,
            rite_options=load_rite_options(),
        )

    @bp.route("/services/new", methods=["GET", "POST"])
    @login_required
    def services_new():
        db = get_db()
        rite = DEFAULT_RITE
        if request.method == "POST":
            mode = request.form.get("mode", "defaults")
            rite = request.form.get("rite") or DEFAULT_RITE
            if mode == "copy":
                raw_source_id = request.form.get("from_service_id")
                try:
                    source_id = int(raw_source_id)
                except (TypeError, ValueError):
                    source_id = None
                if not source_id:
                    return render_error("Select a service to copy.", 400)
                source = db.execute(
                    """
                    select
                      rite,
                      text_order,
                      text_disabled,
                      lesson_overrides,
                      offertory_sentence_id
                    from services
                    where id=? and user_id=? limit 1
                    """,
                    (source_id, g.user["id"]),
                ).fetchone()
                if not source:
                    return render_error("Service not found.", 404)
                if source["rite"] != rite:
                    return render_error("Service rite does not match.", 400)

                payload = blank_service_payload(
                    g.user["id"], source["rite"] or DEFAULT_RITE
                )
                new_service_id = create_service(db, payload)

                custom_rows = db.execute(
                    "select id, title, text, created_at from service_custom_elements where service_id=? and user_id=? order by created_at, id",
                    (source_id, g.user["id"]),
                ).fetchall()
                custom_id_map = {}
                for row in custom_rows:
                    cursor = db.execute(
                        "insert into service_custom_elements (service_id, user_id, title, text) values (?, ?, ?, ?)",
                        (new_service_id, g.user["id"], row["title"], row["text"]),
                    )
                    custom_id_map[row["id"]] = cursor.lastrowid

                def remap_tokens(tokens):
                    remapped = []
                    for token in tokens:
                        if token.startswith("custom:"):
                            try:
                                old_id = int(token.split(":", 1)[1])
                            except (IndexError, ValueError):
                                continue
                            new_id = custom_id_map.get(old_id)
                            if new_id:
                                remapped.append(f"custom:{new_id}")
                            continue
                        remapped.append(token)
                    return remapped

                order_tokens = remap_tokens(parse_plan_tokens(source["text_order"]))
                disabled_tokens = remap_tokens(
                    parse_plan_tokens(source["text_disabled"])
                )
                payload["rite"] = source["rite"] or DEFAULT_RITE
                payload["text_order"] = json.dumps(order_tokens)
                payload["text_disabled"] = json.dumps(disabled_tokens)
                lesson_overrides = _parse_json_object(source["lesson_overrides"])
                if lesson_overrides:
                    payload["lesson_overrides"] = lesson_overrides
                if source["offertory_sentence_id"] is not None:
                    payload["offertory_sentence_id"] = source["offertory_sentence_id"]
                update_service_columns(db, new_service_id, payload)
                db.commit()
                return redirect(url_for("main.service", service_id=new_service_id))
        payload = blank_service_payload(g.user["id"], rite)
        new_service_id = create_service(db, payload)
        db.commit()
        return redirect(url_for("main.service", service_id=new_service_id))

    @bp.route("/service/<int:service_id>")
    @login_required
    def service(service_id, rite=DEFAULT_RITE):
        db = get_db()
        existing_owner = db.execute(
            "select user_id from services where id=? limit 1", (service_id,)
        ).fetchone()
        if not existing_owner or existing_owner["user_id"] != g.user["id"]:
            return render_error("Service not found.", 404)
        context = build_plan_context(
            service_id, rite, g.user["id"], OFFERTORY_DEFAULT_PREFIX
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
        context.update(
            {
                "pco_connected": bool(pco_connection) if pco_enabled else False,
                "pco_link": pco_link,
                "pco_service_types": pco_service_types,
            }
        )
        return render_template("service.html", **context)

    @bp.route("/service")
    @login_required
    def service_missing_id():
        return render_error(
            "Service ID required. Open a service from the Services list.", 400
        )

    @bp.route("/service/<int:service_id>/delete", methods=["POST"])
    @login_required
    def service_delete(service_id):
        db = get_db()
        db.execute(
            "delete from service_custom_elements where service_id=? and user_id=?",
            (service_id, g.user["id"]),
        )
        db.execute(
            "delete from service_shares where service_id=?",
            (service_id,),
        )
        db.execute(
            "delete from services where id=? and user_id=?", (service_id, g.user["id"])
        )
        db.commit()
        return redirect(url_for("main.services"))
