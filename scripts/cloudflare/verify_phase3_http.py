#!/usr/bin/env python3
import json
import re
import sys
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8787"
EMAIL = f"phase3-proof-{int(time.time())}@example.com"
PASSWORD = "Phase3-Proof-Password!"
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def fetch(opener, path, data=None):
    body = urlencode(data).encode() if data is not None else None
    request = Request(f"{BASE_URL}{path}", data=body)
    if body is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    started_at = time.perf_counter()
    response = opener.open(request, timeout=180)
    content = response.read()
    return response, content, (time.perf_counter() - started_at) * 1000


def csrf_token(content):
    match = CSRF_PATTERN.search(content.decode())
    if not match:
        raise AssertionError("CSRF token not found")
    return match.group(1)


def wait_for_health(opener):
    last_error = None
    started_at = time.perf_counter()
    for _attempt in range(90):
        try:
            response, content, _duration = fetch(opener, "/health")
            if response.status == 200 and json.loads(content) == {"status": "ok"}:
                return (time.perf_counter() - started_at) * 1000
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(1)
    raise AssertionError(f"Health endpoint did not become ready: {last_error}")


def verify_session_and_password(opener):
    _response, signup_page, _duration = fetch(opener, "/signup")
    response, _content, _duration = fetch(
        opener,
        "/signup",
        {
            "csrf_token": csrf_token(signup_page),
            "first_name": "Phase",
            "last_name": "Three",
            "email": EMAIL,
            "password": PASSWORD,
        },
    )
    assert urlparse(response.geturl()).path == "/settings"

    fetch(opener, "/logout")
    _response, login_page, _duration = fetch(opener, "/login")
    response, _content, _duration = fetch(
        opener,
        "/login",
        {
            "csrf_token": csrf_token(login_page),
            "email": EMAIL,
            "password": PASSWORD,
        },
    )
    assert urlparse(response.geturl()).path == "/services"


def create_service(opener):
    _response, services_page, _duration = fetch(opener, "/services")
    response, _content, _duration = fetch(
        opener,
        "/services",
        {
            "csrf_token": csrf_token(services_page),
            "add_mode": "single",
            "service_date": "2026-01-04",
            "rite": "Renewed Ancient Text",
            "mode": "defaults",
        },
    )
    path = urlparse(response.geturl()).path
    match = re.fullmatch(r"/service/(\d+)", path)
    if not match:
        raise AssertionError(f"Unexpected service redirect: {path}")
    return int(match.group(1))


def verify_export(opener, service_id, extension, signature):
    response, content, duration_ms = fetch(
        opener, f"/service/{service_id}/export.{extension}"
    )
    assert response.status == 200
    assert content.startswith(signature)
    assert "attachment" in response.headers["Content-Disposition"]
    return {"bytes": len(content), "duration_ms": round(duration_ms, 1)}


def main():
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    cold_start_ms = wait_for_health(opener)
    verify_session_and_password(opener)
    service_id = create_service(opener)
    metrics = {
        "cold_start_ms": round(cold_start_ms, 1),
        "pdf": verify_export(opener, service_id, "pdf", b"%PDF"),
        "docx": verify_export(opener, service_id, "docx", b"PK\x03\x04"),
    }
    print(json.dumps(metrics, sort_keys=True))


if __name__ == "__main__":
    main()
