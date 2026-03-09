import uuid

from flask import flash, g, jsonify, redirect, render_template_string, request, url_for

from .auth_session import login_required
from .db import get_db
from .error_pages import render_error
from .plan_lessons import _resolve_lesson_reference_alternates
from .service_option_registry import (
    is_valid_service_option_value,
    normalize_service_option_value,
)
from .service_planning import build_plan_items, parse_plan_tokens
from .service_store import load_service_payload, update_service_columns
from .text_rendering import build_rendered_ordinaries


PROPER_OVERRIDE_TYPES = {
    "collect_of_the_day": "collect",
    "proper_preface": "proper_preface",
}


def register_service_share_routes(bp):
    def _normalize_option_patch_payload(value):
        if not isinstance(value, dict):
            return None
        output = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                return None
            key = raw_key.strip()
            if not key:
                return None
            output[key] = raw_value
        return output

    def _apply_option_patch(rite, existing_values, patch_values):
        merged = dict(existing_values or {})
        for option_key, raw_value in patch_values.items():
            option_value = normalize_service_option_value(option_key, raw_value)
            if not is_valid_service_option_value(rite, option_key, option_value):
                return None, f"Invalid option value for {option_key}."
            if option_value is None:
                merged.pop(option_key, None)
            else:
                merged[option_key] = option_value
        return merged, None

    def _normalize_text_value(value):
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    def _normalize_lesson_preview_patch(value):
        if not isinstance(value, dict):
            return None
        lesson_key = _normalize_text_value(value.get("lesson_key"))
        mode = _normalize_text_value(value.get("mode")) or "default"
        custom_passage = _normalize_text_value(value.get("custom_passage"))
        canonical_passage = _normalize_text_value(value.get("canonical_passage"))
        return {
            "lesson_key": lesson_key,
            "mode": mode,
            "custom_passage": custom_passage,
            "canonical_passage": canonical_passage,
        }

    def _normalize_proper_preview_patch(value):
        if not isinstance(value, dict):
            return None
        proper_key = _normalize_text_value(value.get("proper_key"))
        mode = _normalize_text_value(value.get("mode")) or "default"
        raw_text_id = _normalize_text_value(value.get("proper_text_id"))
        return {
            "proper_key": proper_key,
            "mode": mode,
            "proper_text_id": raw_text_id,
        }

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
        canonical_passage = normalize_value(request.form.get("canonical_passage"))

        allowed_keys = {"lesson_1", "psalm", "lesson_2", "gospel"}
        if lesson_key not in allowed_keys:
            if wants_json:
                return jsonify({"ok": False, "error": "Invalid lesson key."}), 400
            return render_error("Invalid lesson key.", 400)
        if mode not in {"default", "custom", "canonical"}:
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
        if mode == "canonical":
            alternate_options = _resolve_lesson_reference_alternates(
                service_data.get("service_date"),
                service_data.get("observance_handle"),
            )
            valid_options = set(alternate_options.get(lesson_key) or [])
            if not canonical_passage or canonical_passage not in valid_options:
                if wants_json:
                    return (
                        jsonify(
                            {
                                "ok": False,
                                "error": "Canonical lesson option is invalid.",
                            }
                        ),
                        400,
                    )
                flash("Canonical lesson option is invalid.", "error")
                return redirect(url_for("main.service", service_id=service_id))
        lesson_overrides = service_data.get("lesson_overrides") or {}
        if mode == "custom":
            lesson_overrides[lesson_key] = custom_passage
        elif mode == "canonical":
            lesson_overrides[lesson_key] = canonical_passage
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

    @bp.route("/service/<int:service_id>/proper-override", methods=["POST"])
    @login_required
    def service_proper_override(service_id):
        def normalize_value(value):
            if value is None:
                return None
            value = value.strip()
            return value or None

        wants_json = "application/json" in request.headers.get("Accept", "")
        proper_key = normalize_value(request.form.get("proper_key"))
        mode = normalize_value(request.form.get("proper_mode")) or "default"
        raw_text_id = normalize_value(request.form.get("proper_text_id"))

        proper_type = PROPER_OVERRIDE_TYPES.get(proper_key)
        if not proper_type:
            if wants_json:
                return jsonify({"ok": False, "error": "Invalid proper key."}), 400
            return render_error("Invalid proper key.", 400)
        if mode not in {"default", "custom"}:
            if wants_json:
                return jsonify({"ok": False, "error": "Invalid proper mode."}), 400
            return render_error("Invalid proper mode.", 400)
        proper_text_id = None
        if mode == "custom":
            try:
                proper_text_id = int(raw_text_id)
            except (TypeError, ValueError):
                proper_text_id = None
            if proper_text_id is None:
                if wants_json:
                    return jsonify({"ok": False, "error": "Select a proper text."}), 400
                flash("Select a proper text.", "error")
                return redirect(url_for("main.service", service_id=service_id))

        db = get_db()
        service_data = load_service_payload(db, service_id, g.user["id"])
        if not service_data:
            if wants_json:
                return jsonify({"ok": False, "error": "Service not found."}), 404
            return render_error("Service not found.", 404)
        if proper_text_id is not None:
            valid = db.execute(
                "select id from texts where id=? and type=? limit 1",
                (proper_text_id, proper_type),
            ).fetchone()
            if not valid:
                if wants_json:
                    return (
                        jsonify({"ok": False, "error": "Proper text not found."}),
                        404,
                    )
                flash("Proper text not found.", "error")
                return redirect(url_for("main.service", service_id=service_id))

        proper_overrides = service_data.get("proper_overrides") or {}
        if mode == "custom":
            proper_overrides[proper_key] = proper_text_id
        else:
            proper_overrides.pop(proper_key, None)
        service_data["proper_overrides"] = proper_overrides
        update_service_columns(db, service_id, service_data)
        db.commit()
        if wants_json:
            return jsonify(
                {
                    "ok": True,
                    "proper_key": proper_key,
                    "mode": mode,
                    "proper_text_id": proper_overrides.get(proper_key),
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

    @bp.route("/service/<int:service_id>/service-option", methods=["POST"])
    @login_required
    def service_option_value(service_id):
        def normalize_value(value):
            if value is None:
                return None
            value = value.strip()
            return value or None

        wants_json = "application/json" in request.headers.get("Accept", "")
        option_key = normalize_value(request.form.get("option_key"))
        option_value = normalize_service_option_value(
            option_key, request.form.get("option_value")
        )

        if not option_key:
            if wants_json:
                return jsonify({"ok": False, "error": "Invalid option key."}), 400
            return render_error("Invalid option key.", 400)

        db = get_db()
        service_data = load_service_payload(db, service_id, g.user["id"])
        if not service_data:
            if wants_json:
                return jsonify({"ok": False, "error": "Service not found."}), 404
            return render_error("Service not found.", 404)

        if not is_valid_service_option_value(
            service_data.get("rite"), option_key, option_value
        ):
            if wants_json:
                return jsonify({"ok": False, "error": "Invalid option value."}), 400
            return render_error("Invalid option value.", 400)

        service_option_values = service_data.get("service_option_values") or {}
        if option_value is None:
            service_option_values.pop(option_key, None)
        else:
            service_option_values[option_key] = option_value
        service_data["service_option_values"] = service_option_values

        update_service_columns(db, service_id, service_data)
        db.commit()
        if wants_json:
            return jsonify(
                {
                    "ok": True,
                    "option_key": option_key,
                    "option_value": option_value,
                }
            )
        return redirect(url_for("main.service", service_id=service_id))

    @bp.route("/service/<int:service_id>/service-options", methods=["POST"])
    @login_required
    def service_option_values(service_id):
        payload = request.get_json(silent=True) or {}
        patch_values = _normalize_option_patch_payload(payload.get("option_values"))
        if patch_values is None:
            return jsonify({"ok": False, "error": "Invalid options payload."}), 400

        db = get_db()
        service_data = load_service_payload(db, service_id, g.user["id"])
        if not service_data:
            return jsonify({"ok": False, "error": "Service not found."}), 404

        merged_values, error_message = _apply_option_patch(
            service_data.get("rite"),
            service_data.get("service_option_values") or {},
            patch_values,
        )
        if error_message:
            return jsonify({"ok": False, "error": error_message}), 400

        service_data["service_option_values"] = merged_values
        update_service_columns(db, service_id, service_data)
        db.commit()
        return jsonify({"ok": True, "service_option_values": merged_values})

    @bp.route("/service/<int:service_id>/service-option-preview", methods=["POST"])
    @login_required
    def service_option_preview(service_id):
        payload = request.get_json(silent=True) or {}
        patch_values = _normalize_option_patch_payload(payload.get("option_values"))
        lesson_patch = _normalize_lesson_preview_patch(payload.get("lesson_override"))
        proper_patch = _normalize_proper_preview_patch(payload.get("proper_override"))
        has_offertory_patch = "offertory_sentence_id" in payload
        raw_offertory_sentence_id = _normalize_text_value(
            payload.get("offertory_sentence_id")
        )
        row_token = (payload.get("row_token") or "").strip()
        if patch_values is None:
            return jsonify({"ok": False, "error": "Invalid options payload."}), 400
        if not row_token:
            return jsonify({"ok": False, "error": "Invalid row token."}), 400

        db = get_db()
        service_data = load_service_payload(db, service_id, g.user["id"])
        if not service_data:
            return jsonify({"ok": False, "error": "Service not found."}), 404

        merged_values, error_message = _apply_option_patch(
            service_data.get("rite"),
            service_data.get("service_option_values") or {},
            patch_values,
        )
        if error_message:
            return jsonify({"ok": False, "error": error_message}), 400

        preview_data = dict(service_data)
        preview_data["service_option_values"] = merged_values
        lesson_overrides = dict(service_data.get("lesson_overrides") or {})
        proper_overrides = dict(service_data.get("proper_overrides") or {})

        if lesson_patch:
            lesson_key = lesson_patch.get("lesson_key")
            mode = lesson_patch.get("mode")
            custom_passage = lesson_patch.get("custom_passage")
            canonical_passage = lesson_patch.get("canonical_passage")
            allowed_keys = {"lesson_1", "psalm", "lesson_2", "gospel"}
            if lesson_key not in allowed_keys:
                return jsonify({"ok": False, "error": "Invalid lesson key."}), 400
            if mode not in {"default", "custom", "canonical"}:
                return jsonify({"ok": False, "error": "Invalid lesson mode."}), 400
            if mode == "custom":
                if not custom_passage:
                    return (
                        jsonify({"ok": False, "error": "Custom passage is required."}),
                        400,
                    )
                lesson_overrides[lesson_key] = custom_passage
            elif mode == "canonical":
                alternate_options = _resolve_lesson_reference_alternates(
                    service_data.get("service_date"),
                    service_data.get("observance_handle"),
                )
                valid_options = set(alternate_options.get(lesson_key) or [])
                if not canonical_passage or canonical_passage not in valid_options:
                    return (
                        jsonify(
                            {
                                "ok": False,
                                "error": "Canonical lesson option is invalid.",
                            }
                        ),
                        400,
                    )
                lesson_overrides[lesson_key] = canonical_passage
            else:
                lesson_overrides.pop(lesson_key, None)
            preview_data["lesson_overrides"] = lesson_overrides

        if proper_patch:
            proper_key = proper_patch.get("proper_key")
            mode = proper_patch.get("mode")
            proper_type = PROPER_OVERRIDE_TYPES.get(proper_key)
            if not proper_type:
                return jsonify({"ok": False, "error": "Invalid proper key."}), 400
            if mode not in {"default", "custom"}:
                return jsonify({"ok": False, "error": "Invalid proper mode."}), 400
            if mode == "custom":
                try:
                    proper_text_id = int(proper_patch.get("proper_text_id") or "")
                except (TypeError, ValueError):
                    proper_text_id = None
                if proper_text_id is None:
                    return jsonify({"ok": False, "error": "Select a proper text."}), 400
                valid = db.execute(
                    "select id from texts where id=? and type=? limit 1",
                    (proper_text_id, proper_type),
                ).fetchone()
                if not valid:
                    return (
                        jsonify({"ok": False, "error": "Proper text not found."}),
                        404,
                    )
                proper_overrides[proper_key] = proper_text_id
            else:
                proper_overrides.pop(proper_key, None)
            preview_data["proper_overrides"] = proper_overrides

        if has_offertory_patch:
            try:
                sentence_id = int(raw_offertory_sentence_id)
            except (TypeError, ValueError):
                sentence_id = None
            if raw_offertory_sentence_id and sentence_id is None:
                return (
                    jsonify({"ok": False, "error": "Invalid offertory selection."}),
                    400,
                )
            if sentence_id is not None:
                valid = db.execute(
                    "select id from texts where id=? and type=? limit 1",
                    (sentence_id, "offertory_sentence"),
                ).fetchone()
                if not valid:
                    return (
                        jsonify(
                            {"ok": False, "error": "Offertory sentence not found."}
                        ),
                        404,
                    )
            preview_data["offertory_sentence_id"] = sentence_id

        order_tokens = parse_plan_tokens(service_data.get("text_order"))
        disabled_tokens = parse_plan_tokens(service_data.get("text_disabled"))
        plan_items = build_plan_items(
            service_id,
            service_data.get("rite"),
            order_tokens,
            disabled_tokens,
            user_id=g.user["id"],
        )
        enabled_items = [item for item in plan_items if not item.get("disabled")]
        row_item = next(
            (item for item in enabled_items if item.get("token") == row_token), None
        )
        if not row_item:
            return jsonify({"ok": False, "error": "Plan row not found."}), 404

        preview_service = {
            "text_order": service_data.get("text_order"),
            "text_disabled": service_data.get("text_disabled"),
            "season": service_data.get("season"),
            "rite": service_data.get("rite"),
            "service_date": service_data.get("service_date"),
        }
        rendered_ordinaries = build_rendered_ordinaries(
            service_id,
            preview_service,
            {
                "observance_handle": preview_data.get("observance_handle"),
                "lesson_overrides": preview_data.get("lesson_overrides") or {},
                "offertory_sentence_id": preview_data.get("offertory_sentence_id"),
                "proper_overrides": preview_data.get("proper_overrides") or {},
                "default_bible_translation": preview_data.get(
                    "owner_default_bible_translation"
                ),
                "service_option_values": preview_data.get("service_option_values")
                or {},
            },
            user_id=g.user["id"],
        )
        if not rendered_ordinaries:
            return jsonify({"ok": False, "error": "Plan row not found."}), 404
        preview_row = next(
            (
                item
                for item in rendered_ordinaries
                if (item.get("token") or "") == row_token
            ),
            None,
        )
        if not preview_row:
            preview_option_values = preview_data.get("service_option_values") or {}
            penitential_mode = preview_option_values.get("penitential_song.mode")
            source_title = (row_item.get("title") or "").strip()
            alternate_title = None
            if source_title == "The Kyrie" and penitential_mode == "trisagion":
                alternate_title = "The Trisagion"
            elif source_title == "The Trisagion" and penitential_mode != "trisagion":
                alternate_title = "The Kyrie"
            if alternate_title:
                preview_row = next(
                    (
                        item
                        for item in rendered_ordinaries
                        if (item.get("title") or "").strip() == alternate_title
                    ),
                    None,
                )
        if not preview_row:
            return jsonify(
                {
                    "ok": True,
                    "title": row_item.get("title") or "",
                    "preview_html": "<p>This element is omitted by current selections.</p>",
                }
            )
        preview_text = preview_row.get("text") or ""
        if preview_row.get("type") == "custom":
            preview_html = render_template_string(
                "{{ value | markdown_user | trailing_indent }}",
                value=preview_text,
            )
        else:
            preview_html = render_template_string(
                "{{ value | markdown_template | trailing_indent }}",
                value=preview_text,
            )
        return jsonify(
            {
                "ok": True,
                "title": preview_row.get("title") or row_item.get("title") or "",
                "preview_html": preview_html,
                "is_custom": preview_row.get("type") == "custom",
            }
        )
