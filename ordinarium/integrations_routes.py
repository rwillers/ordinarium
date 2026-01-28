import secrets

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    g,
)

from .auth_session import login_required
from .db import get_db
from .pco_client import (
    PcoAuthError,
    build_authorize_url,
    exchange_code_for_token,
)
from .pco_store import delete_pco_connection, get_pco_connection, upsert_pco_connection
from .feature_flags import FEATURE_PCO_SYNC, user_has_feature
from .error_pages import render_error


def _pco_redirect_uri():
    configured = current_app.config.get("PCO_OAUTH_REDIRECT_URI")
    if configured:
        return configured
    return url_for("main.pco_oauth_callback", _external=True)


def register_integration_routes(bp):
    def _require_pco_feature():
        if not user_has_feature(g.user, FEATURE_PCO_SYNC):
            return render_error("Not found.", 404)
        return None

    @bp.route("/integrations")
    @login_required
    def integrations():
        guard = _require_pco_feature()
        if guard:
            return guard
        connection = get_pco_connection(user_id=g.user["id"])
        return render_template(
            "integrations.html",
            pco_connection=connection,
        )

    @bp.route("/integrations/pco/connect")
    @login_required
    def pco_connect():
        guard = _require_pco_feature()
        if guard:
            return guard
        client_id = current_app.config.get("PCO_CLIENT_ID")
        if not client_id:
            flash("PCO client ID is not configured.", "error")
            return redirect(url_for("main.integrations"))
        state = secrets.token_urlsafe(24)
        session["pco_oauth_state"] = state
        redirect_uri = _pco_redirect_uri()
        scope = current_app.config.get("PCO_OAUTH_SCOPES")
        authorize_url = build_authorize_url(
            client_id,
            redirect_uri,
            scope,
            state,
            current_app.config.get("PCO_OAUTH_AUTHORIZE_URL"),
        )
        return redirect(authorize_url)

    @bp.route("/integrations/pco/callback")
    @login_required
    def pco_oauth_callback():
        guard = _require_pco_feature()
        if guard:
            return guard
        error = request.args.get("error")
        if error:
            flash("PCO authorization failed.", "error")
            return redirect(url_for("main.integrations"))
        state = request.args.get("state")
        expected_state = session.get("pco_oauth_state")
        session.pop("pco_oauth_state", None)
        if not state or state != expected_state:
            flash("PCO authorization state mismatch.", "error")
            return redirect(url_for("main.integrations"))
        code = request.args.get("code")
        if not code:
            flash("PCO authorization code missing.", "error")
            return redirect(url_for("main.integrations"))
        client_id = current_app.config.get("PCO_CLIENT_ID")
        client_secret = current_app.config.get("PCO_CLIENT_SECRET")
        if not client_id or not client_secret:
            flash("PCO client credentials are not configured.", "error")
            return redirect(url_for("main.integrations"))
        try:
            token = exchange_code_for_token(
                client_id,
                client_secret,
                code,
                _pco_redirect_uri(),
                current_app.config.get("PCO_OAUTH_TOKEN_URL"),
            )
        except PcoAuthError:
            flash("PCO authorization failed during token exchange.", "error")
            return redirect(url_for("main.integrations"))
        db = get_db()
        upsert_pco_connection(
            user_id=g.user["id"],
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            token_type=token.token_type,
            scope=token.scope,
            expires_at=token.expires_at,
            db=db,
        )
        db.commit()
        flash("Planning Center connected.", "success")
        return redirect(url_for("main.integrations"))

    @bp.route("/integrations/pco/disconnect", methods=["POST"])
    @login_required
    def pco_disconnect():
        guard = _require_pco_feature()
        if guard:
            return guard
        db = get_db()
        delete_pco_connection(g.user["id"], db=db)
        db.commit()
        flash("Planning Center disconnected.", "success")
        return redirect(url_for("main.integrations"))
