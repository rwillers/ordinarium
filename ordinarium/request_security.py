import secrets

from flask import request, session


def csrf_token_matches(request_token):
    session_token = session.get("_csrf_token")
    if not session_token or not request_token:
        return False
    return secrets.compare_digest(session_token, request_token)


def register_csrf_protection(bp):
    @bp.before_request
    def _enforce_csrf():
        if request.method != "POST":
            return None
        token = (
            request.form.get("csrf_token")
            or request.headers.get("X-CSRF-Token")
            or request.headers.get("X-CSRFToken")
        )
        if not csrf_token_matches(token):
            return ("Invalid CSRF token.", 400)
        return None
