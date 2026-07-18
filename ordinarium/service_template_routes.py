from flask import flash, g, redirect, render_template, request, url_for

from .auth_session import login_required
from .db import get_database_gateway
from .error_pages import render_error
from .service_planning import load_custom_templates


def register_service_template_routes(bp):
    @bp.route("/templates", methods=["GET", "POST"])
    @login_required
    def templates():
        error = None
        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            text_value = (request.form.get("text") or "").strip()
            template_id = (request.form.get("template_id") or "").strip()
            if not title:
                error = "Title is required for a template."
            if template_id:
                try:
                    template_id = int(template_id)
                except (TypeError, ValueError):
                    template_id = None
            if not error:
                db = get_database_gateway()
                if template_id:
                    existing = db.fetch_one(
                        "select id from service_custom_templates where id=? and user_id=? limit 1",
                        (template_id, g.user["id"]),
                    )
                    if not existing:
                        return render_error("Template not found.", 404)
                    db.execute(
                        "update service_custom_templates set title=?, text=?, updated_at=CURRENT_TIMESTAMP where id=? and user_id=?",
                        (title, text_value, template_id, g.user["id"]),
                    )
                else:
                    template_id = db.allocate_id("service_custom_templates")
                    db.execute(
                        "insert into service_custom_templates (id, user_id, title, text) values (?, ?, ?, ?)",
                        (template_id, g.user["id"], title, text_value),
                    )
                return redirect(url_for("main.templates"))

        if error:
            flash(error, "error")
        return render_template(
            "templates.html", templates=load_custom_templates(g.user["id"])
        )

    @bp.route("/templates/<int:template_id>/delete", methods=["POST"])
    @login_required
    def templates_delete(template_id):
        db = get_database_gateway()
        existing = db.fetch_one(
            "select id from service_custom_templates where id=? and user_id=? limit 1",
            (template_id, g.user["id"]),
        )
        if not existing:
            return render_error("Template not found.", 404)
        db.execute(
            "delete from service_custom_templates where id=? and user_id=?",
            (template_id, g.user["id"]),
        )
        return redirect(url_for("main.templates"))

    @bp.route("/templates/bulk-delete", methods=["POST"])
    @login_required
    def templates_bulk_delete():
        raw_ids = request.form.getlist("template_ids")
        template_ids = []
        for raw_id in raw_ids:
            try:
                template_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        if not template_ids:
            flash("No templates selected.", "error")
            return redirect(url_for("main.templates"))

        placeholders = ",".join(["?"] * len(template_ids))
        db = get_database_gateway()
        db.execute(
            f"delete from service_custom_templates where user_id=? and id in ({placeholders})",
            (g.user["id"], *template_ids),
        )
        return redirect(url_for("main.templates"))
