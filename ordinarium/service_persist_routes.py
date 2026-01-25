import json
from datetime import date

from flask import flash, g, jsonify, redirect, render_template, request, url_for

from .auth_session import login_required
from .db import get_db
from .error_pages import render_error
from .liturgical_calendar import resolve_observance, resolve_season
from .service_defaults import DEFAULT_RITE, OFFERTORY_DEFAULT_PREFIX
from .service_planning import (
    build_plan_context,
    normalize_plan_token,
    _resolve_lesson_references,
)
from .service_store import load_service_payload, update_service_columns


def register_service_persist_routes(bp):
    @bp.route("/persist/service", methods=["POST"])
    @login_required
    def persist_service():
        def normalize_value(value):
            if value is None:
                return None
            value = value.strip()
            return value or None

        is_autosave = request.form.get(
            "autosave"
        ) == "1" or "application/json" in request.headers.get("Accept", "")

        service_id = request.form.get("service_id")
        try:
            service_id = int(service_id)
        except (TypeError, ValueError):
            if is_autosave:
                return jsonify({"ok": False, "error": "Service ID is required."}), 400
            return render_error("Service ID is required.", 400)

        raw_order = request.form.get("ids", "")
        order_tokens = []
        if raw_order:
            for value in raw_order.split(","):
                token = normalize_plan_token(value)
                if token:
                    order_tokens.append(token)
        order_json = json.dumps(order_tokens)

        raw_disabled = request.form.get("disabled", "")
        disabled_tokens = []
        if raw_disabled:
            for value in raw_disabled.split(","):
                token = normalize_plan_token(value)
                if token:
                    disabled_tokens.append(token)
        disabled_json = json.dumps(disabled_tokens)

        db = get_db()
        existing_data = load_service_payload(db, service_id, g.user["id"])
        if not existing_data:
            if is_autosave:
                return jsonify({"ok": False, "error": "Service not found."}), 404
            return render_error("Service not found.", 404)
        lesson_overrides = existing_data.get("lesson_overrides") or {}
        payload = {
            "user_id": g.user["id"],
            "title": existing_data.get("title"),
            "rite": existing_data.get("rite", DEFAULT_RITE),
            "season": None,
            "service_date": existing_data.get("service_date"),
            "observance_handle": existing_data.get("observance_handle"),
            "lesson_overrides": lesson_overrides,
            "offertory_sentence_id": existing_data.get("offertory_sentence_id"),
        }
        payload.update(
            {
                "rite": normalize_value(request.form.get("rite")) or payload["rite"],
                "service_date": normalize_value(request.form.get("service_date"))
                or payload["service_date"],
                "text_order": order_json,
                "text_disabled": disabled_json,
                "observance_handle": normalize_value(
                    request.form.get("observance_handle")
                ),
            }
        )
        observance = None
        if payload["service_date"]:
            try:
                observance = resolve_observance(
                    date.fromisoformat(payload["service_date"]),
                    payload["observance_handle"],
                )
            except ValueError:
                observance = None
            if observance:
                payload["observance_handle"] = observance.handle
        if observance:
            payload["title"] = observance.name or observance.alternative_name or ""
        if not payload["service_date"]:
            if is_autosave:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "Service date is required before changes can be saved.",
                        }
                    ),
                    400,
                )
            context = build_plan_context(
                service_id, payload["rite"], g.user["id"], OFFERTORY_DEFAULT_PREFIX
            )
            context["service"]["service_date"] = payload["service_date"] or ""
            flash("Service date is required.", "error")
            return render_template("service.html", **context), 400
        if payload["service_date"]:
            try:
                payload["season"] = resolve_season(
                    date.fromisoformat(payload["service_date"])
                )
            except ValueError:
                payload["season"] = None
        else:
            payload["season"] = None

        update_service_columns(db, service_id, payload)
        db.commit()
        if is_autosave:
            return jsonify(
                {
                    "ok": True,
                    "can_delete": bool(payload.get("service_date")),
                    "can_share": bool(payload.get("service_date")),
                    "observance_handle": payload.get("observance_handle"),
                    "lesson_defaults": _resolve_lesson_references(
                        payload.get("service_date"), payload.get("observance_handle")
                    ),
                }
            )
        action = request.form.get("action", "")
        if action == "generate":
            return redirect(url_for("main.text", service_id=service_id))
        return redirect(url_for("main.service", service_id=service_id))
