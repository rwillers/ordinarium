from flask import flash, g, redirect, render_template, request, url_for

from .auth_session import login_required
from .feature_flags import FEATURE_PCO_SYNC, user_has_feature
from .pco_store import get_pco_connection
from .service_options import load_rite_options
from .user_store import get_user_by_id, update_user_settings
from .user_settings import (
    BIBLE_TRANSLATION_OPTIONS,
    GREETING_RESPONSE_OPTIONS,
    resolve_user_settings,
    validate_user_settings,
)


def register_settings_routes(bp):
    @bp.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        rite_options = load_rite_options()
        pco_enabled = user_has_feature(g.user, FEATURE_PCO_SYNC)
        user_row = get_user_by_id(g.user["id"])
        settings_values = resolve_user_settings(user_row, rite_options)

        if request.method == "POST":
            posted_service_time = (
                request.form.get("default_service_time")
                if pco_enabled
                else settings_values["default_service_time"]
            )
            updated_settings, error = validate_user_settings(
                request.form.get("default_rite"),
                request.form.get("default_bible_translation"),
                posted_service_time,
                request.form.get("greeting_response_form"),
                rite_options,
            )
            if error:
                flash(error, "error")
                settings_values = {
                    "default_rite": (request.form.get("default_rite") or "").strip(),
                    "default_bible_translation": (
                        request.form.get("default_bible_translation") or ""
                    ).strip()
                    or settings_values["default_bible_translation"],
                    "default_service_time": (
                        (request.form.get("default_service_time") or "").strip()
                        if pco_enabled
                        else settings_values["default_service_time"]
                    ),
                    "greeting_response_form": (
                        request.form.get("greeting_response_form") or ""
                    ).strip()
                    or settings_values["greeting_response_form"],
                }
            else:
                update_user_settings(g.user["id"], updated_settings)
                flash("Settings updated.", "success")
                return redirect(url_for("main.settings"))

        pco_connection = get_pco_connection(g.user["id"]) if pco_enabled else None
        return render_template(
            "settings.html",
            rite_options=rite_options,
            bible_translation_options=BIBLE_TRANSLATION_OPTIONS,
            greeting_response_options=GREETING_RESPONSE_OPTIONS,
            settings_values=settings_values,
            pco_enabled=pco_enabled,
            pco_connection=pco_connection,
        )
