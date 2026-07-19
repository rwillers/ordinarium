from flask import (
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from .auth_rate_limit import limiter
from .mail_delivery import send_email
from .password_reset_store import (
    PasswordResetConfigurationError,
    consume_queued_password_reset,
    create_queued_password_reset,
)
from .password_security import hash_password
from .queue_publisher import (
    QueuePublicationError,
    publish_password_reset,
    queue_publishing_is_configured,
)
from .turnstile import turnstile_enabled, verify_turnstile_response
from .user_store import (
    create_password_reset_token,
    get_password_reset_record,
    get_user_by_email,
    get_user_by_id,
    update_user_password,
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
                    if queue_publishing_is_configured():
                        try:
                            queued_reset = create_queued_password_reset(user["id"])
                        except PasswordResetConfigurationError:
                            current_app.logger.exception(
                                "Queued password reset configuration is invalid"
                            )
                        except Exception:
                            # Preserve the same public response for existing,
                            # unknown, and deleted accounts during a D1 outage.
                            current_app.logger.exception(
                                "Unable to persist queued password reset"
                            )
                        else:
                            try:
                                publish_password_reset(
                                    reset_id=queued_reset["reset_id"]
                                )
                            except QueuePublicationError:
                                # The encrypted delivery token remains in D1. The
                                # scheduled reconciler will publish this opaque ID.
                                current_app.logger.warning(
                                    "Queued password reset awaits reconciliation",
                                    extra={"reset_id": queued_reset["reset_id"]},
                                )
                    else:
                        token = create_password_reset_token(user["id"])
                        reset_url = url_for(
                            "main.reset_password", token=token, _external=True
                        )
                        body = (
                            "A password reset was requested for your Ordinarium "
                            "account.\n\n"
                            f"Reset your password: {reset_url}\n\n"
                            "If you did not request this, you can ignore this email."
                        )
                        send_email(
                            user["email"], "Reset your Ordinarium password", body
                        )
                flash(
                    "If an account exists for that email, a reset link is on its way.",
                    "info",
                )
                return redirect(url_for("main.login"))
        if error:
            flash(error, "error")
        return render_template(
            "reset_request.html",
            turnstile_site_key=(
                current_app.config.get("TURNSTILE_SITE_KEY")
                if turnstile_enabled()
                else None
            ),
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
                password_hash = hash_password(password)
                queued_reset_id = record.get("queued_reset_id")
                if queued_reset_id:
                    if not consume_queued_password_reset(token, password_hash):
                        flash("This reset link is invalid or expired.", "error")
                        return redirect(url_for("main.request_password_reset"))
                else:
                    user = get_user_by_id(record["user_id"])
                    if not user:
                        flash("This reset link is invalid or expired.", "error")
                        return redirect(url_for("main.request_password_reset"))
                    update_user_password(user["id"], password_hash)
                flash("Password updated. Please log in.", "info")
                return redirect(url_for("main.login"))
        if error:
            flash(error, "error")
        return render_template(
            "reset_password.html",
            token=token,
            turnstile_site_key=(
                current_app.config.get("TURNSTILE_SITE_KEY")
                if turnstile_enabled()
                else None
            ),
        )
