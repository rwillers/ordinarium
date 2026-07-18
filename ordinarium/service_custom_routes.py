import json

from flask import flash, g, jsonify, redirect, request, url_for

from .auth_session import login_required
from .db import get_database_gateway
from .error_pages import render_error
from .service_defaults import DEFAULT_RITE
from .service_planning import parse_plan_tokens
from .service_store import load_service_payload, update_service_columns


def register_service_custom_routes(bp):
    @bp.route("/service/<int:service_id>/custom-element", methods=["POST"])
    @login_required
    def service_add_custom_element(service_id):
        def normalize_value(value):
            if value is None:
                return None
            value = value.strip()
            return value or None

        title = normalize_value(request.form.get("title"))
        text = request.form.get("text") or ""
        text_value = text.strip()
        rite = normalize_value(request.form.get("rite")) or DEFAULT_RITE
        custom_id = normalize_value(request.form.get("custom_id"))
        insert_after = normalize_value(request.form.get("insert_after"))
        is_autosave = request.form.get(
            "autosave"
        ) == "1" or "application/json" in request.headers.get("Accept", "")
        if custom_id:
            try:
                custom_id = int(custom_id)
            except (TypeError, ValueError):
                custom_id = None
        if not title:
            if is_autosave:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "Title is required for a custom element.",
                        }
                    ),
                    400,
                )
            flash("Title is required for a custom element.", "error")
            return redirect(url_for("main.service", service_id=service_id))

        db = get_database_gateway()
        service_data = load_service_payload(db, service_id, g.user["id"])
        if not service_data:
            if is_autosave:
                return jsonify({"ok": False, "error": "Service not found."}), 404
            return render_error("Service not found.", 404)
        if custom_id:
            element = db.fetch_one(
                "select id from service_custom_elements where id=? and service_id=? and user_id=? limit 1",
                (custom_id, service_id, g.user["id"]),
            )
            if not element:
                if is_autosave:
                    return (
                        jsonify({"ok": False, "error": "Custom element not found."}),
                        404,
                    )
                return render_error("Custom element not found.", 404)
            db.execute(
                "update service_custom_elements set title=?, text=? where id=?",
                (title, text_value, custom_id),
            )
            update_service_columns(db, service_id, service_data)
            if is_autosave:
                return jsonify(
                    {
                        "ok": True,
                        "custom_id": custom_id,
                        "title": title,
                        "text": text_value,
                    }
                )
            return redirect(url_for("main.service", service_id=service_id))

        if not service_data.get("rite"):
            service_data["rite"] = rite

        custom_id = db.allocate_id("service_custom_elements")
        db.execute(
            "insert into service_custom_elements (id, service_id, user_id, title, text) values (?, ?, ?, ?, ?)",
            (custom_id, service_id, g.user["id"], title, text_value),
        )
        custom_token = f"custom:{custom_id}"

        order_tokens = parse_plan_tokens(service_data.get("text_order"))
        if not order_tokens:
            text_rows = db.fetch_all(
                "select id from texts where type=? and filter_type=? and filter_content=? order by default_order",
                ("ordinarium", "rite", service_data["rite"]),
            )
            order_tokens = [f"text:{row['id']}" for row in text_rows]
            custom_rows = db.fetch_all(
                "select id from service_custom_elements where service_id=? and user_id=? order by created_at, id",
                (service_id, g.user["id"]),
            )
            order_tokens.extend([f"custom:{row['id']}" for row in custom_rows])
        else:
            order_tokens = [token for token in order_tokens if token != custom_token]
            order_tokens.append(custom_token)
        if insert_after:
            order_tokens = [token for token in order_tokens if token != custom_token]
            try:
                insert_index = order_tokens.index(insert_after)
            except ValueError:
                order_tokens.append(custom_token)
            else:
                order_tokens.insert(insert_index + 1, custom_token)
        service_data["text_order"] = json.dumps(order_tokens)

        update_service_columns(db, service_id, service_data)
        if is_autosave:
            return jsonify(
                {
                    "ok": True,
                    "custom_id": custom_id,
                    "title": title,
                    "text": text_value,
                    "token": custom_token,
                    "insert_after": insert_after,
                }
            )
        return redirect(url_for("main.service", service_id=service_id))

    @bp.route(
        "/service/<int:service_id>/custom-element/<int:custom_id>/delete",
        methods=["POST"],
    )
    @login_required
    def service_delete_custom_element(service_id, custom_id):
        wants_json = "application/json" in request.headers.get("Accept", "")
        db = get_database_gateway()
        service_data = load_service_payload(db, service_id, g.user["id"])
        if not service_data:
            if wants_json:
                return jsonify({"ok": False, "error": "Service not found."}), 404
            return render_error("Service not found.", 404)
        element = db.fetch_one(
            "select id from service_custom_elements where id=? and service_id=? and user_id=? limit 1",
            (custom_id, service_id, g.user["id"]),
        )
        if not element:
            if wants_json:
                return jsonify({"ok": False, "error": "Custom element not found."}), 404
            return render_error("Custom element not found.", 404)
        db.execute(
            "delete from service_custom_elements where id=? and service_id=? and user_id=?",
            (custom_id, service_id, g.user["id"]),
        )

        token = f"custom:{custom_id}"
        order_tokens = parse_plan_tokens(service_data.get("text_order"))
        disabled_tokens = parse_plan_tokens(service_data.get("text_disabled"))
        if order_tokens:
            order_tokens = [value for value in order_tokens if value != token]
            service_data["text_order"] = json.dumps(order_tokens)
        if disabled_tokens:
            disabled_tokens = [value for value in disabled_tokens if value != token]
            service_data["text_disabled"] = json.dumps(disabled_tokens)
        update_service_columns(db, service_id, service_data)
        if wants_json:
            return jsonify({"ok": True, "custom_id": custom_id, "token": token})
        return redirect(url_for("main.service", service_id=service_id))
