from flask import flash, g, redirect, render_template, request, url_for
from flask_login import logout_user

from .auth_session import login_required
from .password_security import hash_password
from .user_store import get_user_by_email, get_user_by_id, update_user_profile


def register_account_routes(bp):
    @bp.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("main.index"))

    @bp.route("/account", methods=["GET", "POST"])
    @login_required
    def account():
        error = None
        user = get_user_by_id(g.user["id"])
        if request.method == "POST":
            first_name = (request.form.get("first_name") or "").strip()
            last_name = (request.form.get("last_name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            if not first_name or not last_name or not email:
                error = "Name and email are required."
            else:
                existing = get_user_by_email(email)
                if existing and existing["id"] != g.user["id"]:
                    error = "An account with this email already exists."
            if password and len(password) < 8:
                error = "Password must be at least 8 characters."
            if not error:
                password_hash = user["password_hash"] if user else None
                if password:
                    password_hash = hash_password(password)
                update_user_profile(
                    g.user["id"],
                    first_name,
                    last_name,
                    email,
                    password_hash,
                )
                return redirect(url_for("main.account"))
        if error:
            flash(error, "error")
        return render_template(
            "account.html",
            first_name=user["first_name"] if user else "",
            last_name=user["last_name"] if user else "",
            email=user["email"] if user else "",
        )
