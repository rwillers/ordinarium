import uuid

from flask import flash, g, jsonify, redirect, request, url_for

from .auth_session import login_required
from .db import get_db
from .error_pages import render_error
from .service_store import load_service_payload, update_service_columns


def register_service_share_routes(bp):
    @bp.route("/service/<int:service_id>/share", methods=["POST"])
    @login_required
    def service_share(service_id):
        db = get_db()
        existing_owner = db.execute(
            "select user_id from services where id=? limit 1", (service_id,)
        ).fetchone()
        if not existing_owner or existing_owner["user_id"] != g.user["id"]:
            return render_error("Service not found.", 404)
        existing_share = db.execute(
            "select share_uuid from service_shares where service_id=? limit 1",
            (service_id,),
        ).fetchone()
        if existing_share:
            share_uuid = existing_share["share_uuid"]
            created = False
        else:
            share_uuid = str(uuid.uuid4())
            db.execute(
                "insert into service_shares (service_id, share_uuid) values (?, ?)",
                (service_id, share_uuid),
            )
            db.commit()
            created = True
        share_url = url_for("main.shared_text", share_uuid=share_uuid, _external=True)
        return jsonify(
            {"share_uuid": share_uuid, "share_url": share_url, "created": created}
        )

    @bp.route("/service/<int:service_id>/lesson-passage", methods=["POST"])
    @login_required
    def service_lesson_passage(service_id):
        def normalize_value(value):
            if value is None:
                return None
            value = value.strip()
            return value or None

        wants_json = "application/json" in request.headers.get("Accept", "")
        lesson_key = normalize_value(request.form.get("lesson_key"))
        mode = normalize_value(request.form.get("lesson_mode")) or "default"
        custom_passage = normalize_value(request.form.get("custom_passage"))

        allowed_keys = {"lesson_1", "psalm", "lesson_2", "gospel"}
        if lesson_key not in allowed_keys:
            if wants_json:
                return jsonify({"ok": False, "error": "Invalid lesson key."}), 400
            return render_error("Invalid lesson key.", 400)
        if mode not in {"default", "custom"}:
            if wants_json:
                return jsonify({"ok": False, "error": "Invalid lesson mode."}), 400
            return render_error("Invalid lesson mode.", 400)
        if mode == "custom" and not custom_passage:
            if wants_json:
                return (
                    jsonify({"ok": False, "error": "Custom passage is required."}),
                    400,
                )
            flash("Custom passage is required.", "error")
            return redirect(url_for("main.service", service_id=service_id))

        db = get_db()
        service_data = load_service_payload(db, service_id, g.user["id"])
        if not service_data:
            if wants_json:
                return jsonify({"ok": False, "error": "Service not found."}), 404
            return render_error("Service not found.", 404)
        lesson_overrides = service_data.get("lesson_overrides") or {}
        if mode == "custom":
            lesson_overrides[lesson_key] = custom_passage
        else:
            lesson_overrides.pop(lesson_key, None)
        service_data["lesson_overrides"] = lesson_overrides
        update_service_columns(db, service_id, service_data)
        db.commit()
        if wants_json:
            return jsonify(
                {
                    "ok": True,
                    "lesson_key": lesson_key,
                    "mode": mode,
                    "custom_passage": lesson_overrides.get(lesson_key),
                }
            )
        return redirect(url_for("main.service", service_id=service_id))

    @bp.route("/service/<int:service_id>/offertory-sentence", methods=["POST"])
    @login_required
    def service_offertory_sentence(service_id):
        def normalize_value(value):
            if value is None:
                return None
            value = value.strip()
            return value or None

        wants_json = "application/json" in request.headers.get("Accept", "")
        raw_sentence_id = normalize_value(request.form.get("offertory_sentence_id"))
        sentence_id = None
        if raw_sentence_id:
            try:
                sentence_id = int(raw_sentence_id)
            except (TypeError, ValueError):
                sentence_id = None
        if raw_sentence_id and sentence_id is None:
            if wants_json:
                return (
                    jsonify({"ok": False, "error": "Invalid offertory selection."}),
                    400,
                )
            flash("Invalid offertory selection.", "error")
            return redirect(url_for("main.service", service_id=service_id))

        db = get_db()
        service_data = load_service_payload(db, service_id, g.user["id"])
        if not service_data:
            if wants_json:
                return jsonify({"ok": False, "error": "Service not found."}), 404
            return render_error("Service not found.", 404)
        if sentence_id is not None:
            valid = db.execute(
                "select id from texts where id=? and type=? limit 1",
                (sentence_id, "offertory_sentence"),
            ).fetchone()
            if not valid:
                if wants_json:
                    return (
                        jsonify(
                            {"ok": False, "error": "Offertory sentence not found."}
                        ),
                        404,
                    )
                flash("Offertory sentence not found.", "error")
                return redirect(url_for("main.service", service_id=service_id))

        if sentence_id is None:
            service_data["offertory_sentence_id"] = None
        else:
            service_data["offertory_sentence_id"] = sentence_id
        update_service_columns(db, service_id, service_data)
        db.commit()
        if wants_json:
            return jsonify({"ok": True, "offertory_sentence_id": sentence_id})
        return redirect(url_for("main.service", service_id=service_id))
