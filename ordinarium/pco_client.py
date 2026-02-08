from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

DEFAULT_API_BASE = "https://api.planningcenteronline.com"
DEFAULT_OAUTH_AUTHORIZE_URL = "https://api.planningcenteronline.com/oauth/authorize"
DEFAULT_OAUTH_TOKEN_URL = "https://api.planningcenteronline.com/oauth/token"

JSON_API_HEADERS = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json",
}


@dataclass
class PcoToken:
    access_token: str
    refresh_token: str | None = None
    token_type: str | None = None
    scope: str | None = None
    expires_at: str | None = None


class PcoApiError(RuntimeError):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class PcoAuthError(RuntimeError):
    pass


def build_authorize_url(
    client_id,
    redirect_uri,
    scope,
    state,
    authorize_url=DEFAULT_OAUTH_AUTHORIZE_URL,
):
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    if scope:
        params["scope"] = scope
    return f"{authorize_url}?{urlencode(params)}"


def exchange_code_for_token(
    client_id,
    client_secret,
    code,
    redirect_uri,
    token_url=DEFAULT_OAUTH_TOKEN_URL,
):
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    response = requests.post(token_url, data=data, timeout=20)
    if response.status_code >= 400:
        raise PcoAuthError(f"OAuth token exchange failed ({response.status_code}).")
    payload = response.json()
    return _token_from_payload(payload)


def refresh_access_token(
    client_id,
    client_secret,
    refresh_token,
    token_url=DEFAULT_OAUTH_TOKEN_URL,
):
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    response = requests.post(token_url, data=data, timeout=20)
    if response.status_code >= 400:
        raise PcoAuthError(f"OAuth token refresh failed ({response.status_code}).")
    payload = response.json()
    return _token_from_payload(payload)


def _token_from_payload(payload):
    expires_in = payload.get("expires_in")
    expires_at = None
    if expires_in:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        ).isoformat()
    return PcoToken(
        access_token=payload.get("access_token"),
        refresh_token=payload.get("refresh_token"),
        token_type=payload.get("token_type"),
        scope=payload.get("scope"),
        expires_at=expires_at,
    )


def token_needs_refresh(expires_at, buffer_seconds=60):
    if not expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(expires_at)
    except ValueError:
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= (expiry - timedelta(seconds=buffer_seconds))


def api_request(
    method,
    base_url,
    path,
    access_token,
    json=None,
    params=None,
    absolute_url=False,
):
    url = path if absolute_url else f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    headers = dict(JSON_API_HEADERS)
    headers["Authorization"] = f"Bearer {access_token}"
    response = requests.request(
        method,
        url,
        headers=headers,
        json=json,
        params=params,
        timeout=30,
    )
    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            payload = {"detail": response.text}
        detail = _format_api_error_detail(payload)
        message = f"PCO API request failed ({response.status_code})."
        if detail:
            message = f"{message} {detail}"
        raise PcoApiError(
            message,
            status_code=response.status_code,
            payload=payload,
        )
    if response.status_code == 204:
        return None
    return response.json()


def _format_api_error_detail(payload):
    if not payload:
        return ""
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        parts = []
        for error in errors:
            if not isinstance(error, dict):
                continue
            title = error.get("title")
            detail = error.get("detail")
            source = error.get("source") or {}
            pointer = source.get("pointer")
            segment = ": ".join([value for value in (title, detail) if value])
            if pointer:
                segment = f"{segment} ({pointer})" if segment else pointer
            if segment:
                parts.append(segment)
        return " | ".join(parts)
    detail = payload.get("detail")
    if isinstance(detail, str):
        return detail
    return ""


def list_all_pages(fetch_page):
    data = []
    next_url = None
    while True:
        payload = fetch_page(next_url)
        if not payload:
            break
        page_data = payload.get("data") or []
        data.extend(page_data)
        links = payload.get("links") or {}
        next_url = links.get("next")
        if not next_url:
            break
    return data


def fetch_services_organization_name(base_url, access_token):
    payload = api_request(
        "GET",
        base_url or DEFAULT_API_BASE,
        "/services/v2",
        access_token,
    )
    data = (payload or {}).get("data") or {}
    attributes = data.get("attributes") or {}
    name = attributes.get("name")
    if not isinstance(name, str):
        return None
    normalized = name.strip()
    return normalized or None
