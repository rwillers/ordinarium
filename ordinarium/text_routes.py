from io import BytesIO

from flask import current_app, g, send_file

from .auth_session import login_required
from .db import get_db
from .document_service_client import render_document
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
            docx_bytes = _render_docx_export(context)
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
        try:
            saved_service, saved_data = load_service_for_text(service_id, g.user["id"])
            context = build_text_export_context(
                service_id, saved_service, saved_data, user_id=g.user["id"]
            )
            if not context:
                return render_error("Service ID required to generate text.", 400)
            html_text = render_text_export_html(context)
            pdf_bytes = _render_pdf_export(html_text)
        except RuntimeError as exc:
            current_app.logger.exception(
                "PDF export runtime error for service %s", service_id
            )
            return render_error("Unable to generate PDF at this time.", 503)
        except Exception as exc:
            current_app.logger.exception(
                "PDF export unexpected error for service %s", service_id
            )
            return render_error("Unable to generate PDF at this time.", 503)
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


def _render_docx_export(context):
    if current_app.config.get("DOCUMENT_SERVICE_URL"):
        return render_document("docx", {"context": context})
    return render_docx_bytes(context)


def _render_pdf_export(html_text):
    if current_app.config.get("DOCUMENT_SERVICE_URL"):
        return render_document("pdf", {"html": html_text})
    return render_pdf_bytes(html_text, base_url=current_app.root_path)
