from urllib.parse import urljoin, urlparse

from flask import (
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_user
from werkzeug.security import check_password_hash, generate_password_hash

from .auth_rate_limit import limiter
from .db import get_db
from .auth_session import build_user
from .turnstile import turnstile_enabled, verify_turnstile_response
from .user_store import get_user_by_email


def register_login_routes(bp):
    @bp.route("/login", methods=["GET", "POST"])
    @limiter.limit(lambda: current_app.config.get("RATELIMIT_LOGIN", "10/minute"))
    def login():
        if g.user:
            return redirect(url_for("main.services"))
        error = None
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            if not email or not password:
                error = "Email and password are required."
            else:
                user = get_user_by_email(email)
                if not user:
                    error = "Invalid email or password."
                else:
                    password_hash = user["password_hash"]
                    if not password_hash or not check_password_hash(
                        password_hash, password
                    ):
                        error = "Invalid email or password."
            if not error and turnstile_enabled():
                token = request.form.get("cf-turnstile-response")
                verified, _ = verify_turnstile_response(token, request.remote_addr)
                if not verified:
                    error = "Please verify you're human."
            if not error and user:
                login_user(build_user(user))
                next_url = (
                    request.form.get("next")
                    or request.args.get("next")
                    or url_for("main.services")
                )
                return redirect(_safe_redirect_target(next_url))
        if error:
            flash(error, "error")
        return render_template(
            "login.html",
            turnstile_site_key=current_app.config.get("TURNSTILE_SITE_KEY"),
        )

    @bp.route("/signup", methods=["GET", "POST"])
    @limiter.limit(lambda: current_app.config.get("RATELIMIT_SIGNUP", "10/minute"))
    def signup():
        if g.user:
            return redirect(url_for("main.services"))
        error = None
        if request.method == "POST":
            first_name = (request.form.get("first_name") or "").strip()
            last_name = (request.form.get("last_name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            if not first_name or not last_name or not email or not password:
                error = "All fields are required."
            elif len(password) < 8:
                error = "Password must be at least 8 characters."
            elif get_user_by_email(email):
                error = "An account with this email already exists."
            if not error and turnstile_enabled():
                token = request.form.get("cf-turnstile-response")
                verified, _ = verify_turnstile_response(token, request.remote_addr)
                if not verified:
                    error = "Please verify you're human."
            if not error:
                db = get_db()
                db.execute(
                    "insert into users (first_name, last_name, email, password_hash) values (?, ?, ?, ?)",
                    (first_name, last_name, email, generate_password_hash(password)),
                )
                db.commit()
                user = get_user_by_email(email)
                login_user(build_user(user))
                return redirect(url_for("main.services"))
        if error:
            flash(error, "error")
        return render_template(
            "signup.html",
            turnstile_site_key=current_app.config.get("TURNSTILE_SITE_KEY"),
        )


def _safe_redirect_target(target, fallback_endpoint="main.services"):
    if not target:
        return url_for(fallback_endpoint)
    if target.startswith(("//", "\\\\")):
        return url_for(fallback_endpoint)
    host_url = request.host_url
    ref_url = urlparse(host_url)
    test_url = urlparse(urljoin(host_url, target))
    if test_url.scheme not in ("http", "https"):
        return url_for(fallback_endpoint)
    if ref_url.netloc != test_url.netloc:
        return url_for(fallback_endpoint)
    safe_path = test_url.path
    if test_url.query:
        safe_path = f"{safe_path}?{test_url.query}"
    if test_url.fragment:
        safe_path = f"{safe_path}#{test_url.fragment}"
    return safe_path
