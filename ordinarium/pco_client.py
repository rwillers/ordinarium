from __future__ import annotations

from dataclasses import dataclass
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import hashlib
import re
import threading
import time
from urllib.parse import urlencode

import requests

DEFAULT_API_BASE = "https://api.planningcenteronline.com"
DEFAULT_OAUTH_AUTHORIZE_URL = "https://api.planningcenteronline.com/oauth/authorize"
DEFAULT_OAUTH_TOKEN_URL = "https://api.planningcenteronline.com/oauth/token"

JSON_API_HEADERS = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json",
}

DEFAULT_RATE_LIMIT = 100
DEFAULT_RATE_PERIOD_SECONDS = 20
MAX_RATE_LIMIT_RETRIES = 3


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


@dataclass
class _RateLimitBucket:
    limit: int = DEFAULT_RATE_LIMIT
    period_seconds: float = DEFAULT_RATE_PERIOD_SECONDS
    count: int = 0
    window_started_at: float = 0
    blocked_until: float = 0


class PcoRateLimiter:
    def __init__(
        self,
        default_limit=DEFAULT_RATE_LIMIT,
        default_period_seconds=DEFAULT_RATE_PERIOD_SECONDS,
        sleep_func=time.sleep,
        monotonic_func=time.monotonic,
    ):
        self.default_limit = default_limit
        self.default_period_seconds = default_period_seconds
        self.sleep = sleep_func
        self.monotonic = monotonic_func
        self._buckets = {}
        self._lock = threading.Lock()

    def wait_for_slot(self, token):
        delay = self._reserve_delay(token)
        remaining = _deadline_remaining_seconds()
        if remaining is not None and delay >= remaining:
            raise requests.Timeout("Planning Center job deadline was exceeded.")
        if delay > 0:
            self.sleep(delay)

    def update_from_response(self, token, response):
        headers = response.headers or {}
        retry_after = _parse_retry_after(headers.get("Retry-After"))
        limit = _parse_positive_int(headers.get("X-PCO-API-Request-Rate-Limit"))
        count = _parse_positive_int(headers.get("X-PCO-API-Request-Rate-Count"))
        period = _parse_rate_period(headers.get("X-PCO-API-Request-Rate-Period"))
        now = self.monotonic()
        with self._lock:
            bucket = self._bucket_for_token(token)
            if limit:
                bucket.limit = limit
            if period:
                bucket.period_seconds = period
            if count is not None:
                if now - bucket.window_started_at >= bucket.period_seconds:
                    bucket.window_started_at = now
                bucket.count = max(bucket.count, count)
            if response.status_code == 429:
                wait_seconds = retry_after or bucket.period_seconds
                bucket.blocked_until = max(bucket.blocked_until, now + wait_seconds)

    def reset(self):
        with self._lock:
            self._buckets = {}

    def _reserve_delay(self, token):
        with self._lock:
            now = self.monotonic()
            bucket = self._bucket_for_token(token)
            if not bucket.window_started_at:
                bucket.window_started_at = now
            window_age = now - bucket.window_started_at
            if window_age >= bucket.period_seconds:
                bucket.window_started_at = now
                bucket.count = 0
                window_age = 0
            delay = max(0, bucket.blocked_until - now)
            if bucket.count >= bucket.limit:
                delay = max(delay, bucket.period_seconds - window_age)
                bucket.window_started_at = now + delay
                bucket.count = 0
            bucket.count += 1
            return delay

    def _bucket_for_token(self, token):
        key = _rate_limit_token_key(token)
        if key not in self._buckets:
            self._buckets[key] = _RateLimitBucket(
                limit=self.default_limit,
                period_seconds=self.default_period_seconds,
            )
        return self._buckets[key]


rate_limiter = PcoRateLimiter()
_request_deadline = ContextVar("pco_request_deadline", default=None)


def begin_pco_request_deadline(seconds):
    return _request_deadline.set(time.monotonic() + float(seconds))


def end_pco_request_deadline(token):
    _request_deadline.reset(token)


def _rate_limit_token_key(token):
    if not token:
        return "anonymous"
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _parse_positive_int(value):
    if value is None:
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _parse_retry_after(value):
    parsed = _parse_positive_int(value)
    if parsed is None:
        return None
    return parsed


def _parse_rate_period(value):
    if value is None:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(value))
    if not match:
        return None
    try:
        seconds = float(match.group(1))
    except ValueError:
        return None
    if seconds <= 0:
        return None
    return seconds


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
        if response.status_code == 429 or response.status_code >= 500:
            try:
                payload = response.json()
            except ValueError:
                payload = {"detail": response.text}
            raise PcoApiError(
                f"OAuth token refresh failed ({response.status_code}).",
                status_code=response.status_code,
                payload=payload,
            )
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
    retries = 0
    while True:
        rate_limiter.wait_for_slot(access_token)
        timeout_seconds = _remaining_request_seconds()
        response = requests.request(
            method,
            url,
            headers=headers,
            json=json,
            params=params,
            timeout=timeout_seconds,
        )
        rate_limiter.update_from_response(access_token, response)
        if response.status_code != 429 or retries >= MAX_RATE_LIMIT_RETRIES:
            break
        retries += 1
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


def _remaining_request_seconds():
    remaining = _deadline_remaining_seconds()
    if remaining is None:
        return 30
    if remaining <= 0:
        raise requests.Timeout("Planning Center job deadline was exceeded.")
    return max(1, min(20, remaining))


def _deadline_remaining_seconds():
    deadline = _request_deadline.get()
    return None if deadline is None else deadline - time.monotonic()


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
