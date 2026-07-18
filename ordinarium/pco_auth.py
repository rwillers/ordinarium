from flask import current_app

from .pco_client import PcoAuthError, refresh_access_token, token_needs_refresh
from .pco_store import get_pco_connection, upsert_pco_connection


def get_valid_pco_connection(user_id, db=None):
    connection = get_pco_connection(user_id, db=db)
    if not connection:
        return None
    if token_needs_refresh(connection["expires_at"]):
        refresh_token = connection["refresh_token"]
        if not refresh_token:
            raise PcoAuthError("Missing refresh token.")
        client_id = current_app.config.get("PCO_CLIENT_ID")
        client_secret = current_app.config.get("PCO_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise PcoAuthError("PCO client credentials are not configured.")
        token = refresh_access_token(
            client_id,
            client_secret,
            refresh_token,
            current_app.config.get("PCO_OAUTH_TOKEN_URL"),
        )
        upsert_pco_connection(
            user_id,
            token.access_token,
            token.refresh_token,
            token.token_type,
            token.scope,
            token.expires_at,
            db=db,
        )
        if hasattr(db, "commit"):
            db.commit()
        connection = get_pco_connection(user_id, db=db)
    return connection
