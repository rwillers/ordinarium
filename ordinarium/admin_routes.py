import json
from datetime import datetime

from flask import flash, g, redirect, render_template, request, url_for

from .auth_session import login_required
from .db import get_db
from .error_pages import render_error
from .feature_flags import FEATURE_ADMIN, list_feature_flags, parse_feature_flags
from .user_store import get_user_by_email, get_user_by_id


def register_admin_routes(bp):
    def _require_admin():
        if not g.user or not g.user.has_feature(FEATURE_ADMIN):
            return render_error("Not found.", 404)
        return None

    @bp.route("/admin")
    @login_required
    def admin_index():
        guard = _require_admin()
        if guard:
            return guard
        db = get_db()
        rows = db.execute(
            """
            select id, first_name, last_name, email, feature_flags
            from users
            where deleted_at is null
            order by id asc
            """
        ).fetchall()
        users = []
        for row in rows:
            users.append(
                {
                    "id": row["id"],
                    "first_name": row["first_name"] or "",
                    "last_name": row["last_name"] or "",
                    "email": row["email"] or "",
                    "feature_flags": parse_feature_flags(row["feature_flags"]),
                }
            )
        return render_template("admin.html", users=users)

    @bp.route("/admin/users/<int:user_id>", methods=["GET", "POST"])
    @login_required
    def admin_user_edit(user_id):
        guard = _require_admin()
        if guard:
            return guard
        user = get_user_by_id(user_id)
        if not user:
            return render_error("User not found.", 404)
        flags = parse_feature_flags(user["feature_flags"])
        if request.method == "POST":
            first_name = (request.form.get("first_name") or "").strip()
            last_name = (request.form.get("last_name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            if not first_name or not last_name or not email:
                flash("Name and email are required.", "error")
                return redirect(url_for("main.admin_user_edit", user_id=user_id))
            existing = get_user_by_email(email)
            if existing and existing["id"] != user_id:
                flash("An account with this email already exists.", "error")
                return redirect(url_for("main.admin_user_edit", user_id=user_id))
            updated_flags = {}
            for entry in list_feature_flags():
                key = entry["key"]
                updated_flags[key] = bool(request.form.get(f"flag_{key}"))
            flags_payload = (
                json.dumps(updated_flags) if any(updated_flags.values()) else None
            )
            db = get_db()
            db.execute(
                """
                update users
                set first_name=?, last_name=?, email=?, feature_flags=?
                where id=?
                """,
                (first_name, last_name, email, flags_payload, user_id),
            )
            db.commit()
            flash("User updated.", "success")
            return redirect(url_for("main.admin_user_edit", user_id=user_id))
        return render_template(
            "admin_user.html",
            user_record=user,
            feature_flags=list_feature_flags(),
            enabled_flags=flags,
        )

    @bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
    @login_required
    def admin_user_delete(user_id):
        guard = _require_admin()
        if guard:
            return guard
        if user_id == g.user["id"]:
            flash("You cannot delete your own account.", "error")
            return redirect(url_for("main.admin_index"))
        db = get_db()
        db.execute(
            "update users set deleted_at=? where id=?",
            (datetime.utcnow().isoformat(), user_id),
        )
        db.commit()
        flash("User deleted.", "success")
        return redirect(url_for("main.admin_index"))

    @bp.route("/admin/users/bulk-delete", methods=["POST"])
    @login_required
    def admin_users_bulk_delete():
        guard = _require_admin()
        if guard:
            return guard
        raw_ids = request.form.getlist("user_ids")
        user_ids = []
        for raw_id in raw_ids:
            try:
                user_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        user_ids = [user_id for user_id in user_ids if user_id != g.user["id"]]
        if not user_ids:
            flash("No users selected.", "error")
            return redirect(url_for("main.admin_index"))

        placeholders = ",".join(["?"] * len(user_ids))
        db = get_db()
        params = [datetime.utcnow().isoformat(), *user_ids]
        db.execute(
            f"update users set deleted_at=? where id in ({placeholders})",
            params,
        )
        db.commit()
        flash("Users deleted.", "success")
        return redirect(url_for("main.admin_index"))
