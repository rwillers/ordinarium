import json
from urllib import parse as urlparse_lib
from urllib import request as urlrequest

from flask import current_app


def turnstile_enabled():
    return bool(current_app.config.get("TURNSTILE_SECRET_KEY")) and bool(
        current_app.config.get("TURNSTILE_SITE_KEY")
    )


def verify_turnstile_response(token, remoteip=None):
    if not turnstile_enabled():
        return True, None
    if not token:
        return False, "missing-input-response"
    data = {
        "secret": current_app.config.get("TURNSTILE_SECRET_KEY"),
        "response": token,
    }
    if remoteip:
        data["remoteip"] = remoteip
    encoded = urlparse_lib.urlencode(data).encode("utf-8")
    request_obj = urlrequest.Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=encoded,
        method="POST",
    )
    request_obj.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlrequest.urlopen(request_obj, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        current_app.logger.warning("Turnstile verification error: %s", exc)
        return False, "verification-error"
    if payload.get("success"):
        return True, None
    current_app.logger.info(
        "Turnstile rejected response: %s", payload.get("error-codes")
    )
    return False, payload.get("error-codes")
