from io import BytesIO

from flask import current_app, g, send_file

from .auth_session import login_required
from .db import get_db
from .error_pages import render_error
from .service_store import load_service_for_text
from .text_rendering import render_text_page
from .text_export import (
    build_export_filename,
    build_text_export_context,
    render_docx_bytes,
    render_pdf_bytes,
    render_text_export_html,
)


def register_text_routes(bp):
    @bp.route("/service/<int:service_id>/view")
    @login_required
    def service_view(service_id):
        saved_service, saved_data = load_service_for_text(service_id, g.user["id"])
        return render_text_page(
            service_id, saved_service, saved_data, user_id=g.user["id"]
        )

    @bp.route("/service/<int:service_id>/export.docx")
    @login_required
    def service_export_docx(service_id):
        saved_service, saved_data = load_service_for_text(service_id, g.user["id"])
        context = build_text_export_context(
            service_id, saved_service, saved_data, user_id=g.user["id"]
        )
        if not context:
            return render_error("Service ID required to generate text.", 400)
        try:
            docx_bytes = render_docx_bytes(context)
        except RuntimeError as exc:
            return render_error(str(exc), 503)
        filename = build_export_filename(context, "docx")
        return send_file(
            BytesIO(docx_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=filename,
        )

    @bp.route("/service/<int:service_id>/export.pdf")
    @login_required
    def service_export_pdf(service_id):
        saved_service, saved_data = load_service_for_text(service_id, g.user["id"])
        context = build_text_export_context(
            service_id, saved_service, saved_data, user_id=g.user["id"]
        )
        if not context:
            return render_error("Service ID required to generate text.", 400)
        html_text = render_text_export_html(context)
        try:
            pdf_bytes = render_pdf_bytes(html_text, base_url=current_app.root_path)
        except RuntimeError as exc:
            return render_error(str(exc), 503)
        filename = build_export_filename(context, "pdf")
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    @bp.route("/share/<share_uuid>")
    def shared_text(share_uuid):
        db = get_db()
        share = db.execute(
            "select service_id from service_shares where share_uuid=? limit 1",
            (share_uuid,),
        ).fetchone()
        if not share:
            return render_error("Share link not found.", 404)
        saved_service, saved_data = load_service_for_text(share["service_id"])
        if not saved_service:
            return render_error("Service not found.", 404)
        return render_text_page(share["service_id"], saved_service, saved_data)
