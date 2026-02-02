from flask import g

from .auth_session import login_required
from .db import get_db
from .error_pages import render_error
from .service_store import load_service_for_text
from .text_rendering import render_text_page


def register_text_routes(bp):
    @bp.route("/service/<int:service_id>/view")
    @login_required
    def service_view(service_id):
        saved_service, saved_data = load_service_for_text(service_id, g.user["id"])
        return render_text_page(
            service_id, saved_service, saved_data, user_id=g.user["id"]
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
