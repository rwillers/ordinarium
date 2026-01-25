from flask import (
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.security import generate_password_hash

from .auth_rate_limit import limiter
from .db import get_db
from .mail_delivery import send_email
from .turnstile import turnstile_enabled, verify_turnstile_response
from .user_store import (
    create_password_reset_token,
    get_password_reset_record,
    get_user_by_email,
    get_user_by_id,
)


def register_password_reset_routes(bp):
    @bp.route("/reset-password", methods=["GET", "POST"])
    @limiter.limit(
        lambda: current_app.config.get("RATELIMIT_PASSWORD_RESET", "5/minute")
    )
    def request_password_reset():
        if g.user:
            return redirect(url_for("main.account"))
        error = None
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            if not email:
                error = "Email address is required."
            if not error and turnstile_enabled():
                token = request.form.get("cf-turnstile-response")
                verified, _ = verify_turnstile_response(token, request.remote_addr)
                if not verified:
                    error = "Please verify you're human."
            if not error:
                user = get_user_by_email(email)
                if user:
                    token = create_password_reset_token(user["id"])
                    reset_url = url_for(
                        "main.reset_password", token=token, _external=True
                    )
                    body = (
                        "A password reset was requested for your Ordinarium account.\n\n"
                        f"Reset your password: {reset_url}\n\n"
                        "If you did not request this, you can ignore this email."
                    )
                    send_email(user["email"], "Reset your Ordinarium password", body)
                flash(
                    "If an account exists for that email, a reset link is on its way.",
                    "info",
                )
                return redirect(url_for("main.login"))
        if error:
            flash(error, "error")
        return render_template(
            "reset_request.html",
            turnstile_site_key=current_app.config.get("TURNSTILE_SITE_KEY"),
        )

    @bp.route("/reset-password/<token>", methods=["GET", "POST"])
    @limiter.limit(
        lambda: current_app.config.get("RATELIMIT_PASSWORD_RESET", "5/minute")
    )
    def reset_password(token):
        record = get_password_reset_record(token)
        if not record:
            flash("This reset link is invalid or expired.", "error")
            return redirect(url_for("main.request_password_reset"))
        error = None
        if request.method == "POST":
            password = request.form.get("password") or ""
            if len(password) < 8:
                error = "Password must be at least 8 characters."
            if not error and turnstile_enabled():
                token_value = request.form.get("cf-turnstile-response")
                verified, _ = verify_turnstile_response(
                    token_value, request.remote_addr
                )
                if not verified:
                    error = "Please verify you're human."
            if not error:
                user = get_user_by_id(record["user_id"])
                if not user:
                    flash("Account not found.", "error")
                    return redirect(url_for("main.request_password_reset"))
                db = get_db()
                db.execute(
                    "update users set password_hash=? where id=?",
                    (generate_password_hash(password), user["id"]),
                )
                db.commit()
                flash("Password updated. Please log in.", "info")
                return redirect(url_for("main.login"))
        if error:
            flash(error, "error")
        return render_template(
            "reset_password.html",
            token=token,
            turnstile_site_key=current_app.config.get("TURNSTILE_SITE_KEY"),
        )
