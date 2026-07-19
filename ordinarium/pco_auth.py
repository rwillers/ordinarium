from flask import current_app

from .pco_client import PcoAuthError, refresh_access_token, token_needs_refresh
from .pco_store import get_pco_connection, upsert_pco_connection
from .pco_store import (
    claim_pco_connection_refresh,
    complete_pco_connection_refresh,
    release_pco_connection_refresh,
)


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
        claim_token = claim_pco_connection_refresh(connection, db=db)
        if not claim_token:
            # Another delivery owns this version. Re-read: it may already have
            # completed, otherwise the caller should retry after the short lease.
            current = get_pco_connection(user_id, db=db)
            if current and not token_needs_refresh(current["expires_at"]):
                return current
            raise PcoAuthError("Planning Center token refresh is already in progress.")
        try:
            token = refresh_access_token(
                client_id,
                client_secret,
                refresh_token,
                current_app.config.get("PCO_OAUTH_TOKEN_URL"),
            )
            if not complete_pco_connection_refresh(
                connection, claim_token, token, db=db
            ):
                raise PcoAuthError("Planning Center token refresh lease was lost.")
        except Exception:
            release_pco_connection_refresh(connection, claim_token, db=db)
            raise
        if hasattr(db, "commit"):
            db.commit()
        connection = get_pco_connection(user_id, db=db)
    return connection
