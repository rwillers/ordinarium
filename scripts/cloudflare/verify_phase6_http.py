#!/usr/bin/env python3
import argparse
import json
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

from docx import Document


CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')
PASSWORD = "Phase6-Proof-Password!"


def fetch(opener, base_url, path, data=None, headers=None):
    body = urlencode(data).encode() if data is not None else None
    request = Request(f"{base_url}{path}", data=body, headers=headers or {})
    if body is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    started_at = time.perf_counter()
    with opener.open(request, timeout=180) as response:
        content = response.read()
        return response, content, (time.perf_counter() - started_at) * 1000


def csrf_token(content):
    match = CSRF_PATTERN.search(content.decode())
    if not match:
        raise AssertionError("CSRF token not found")
    return match.group(1)


def create_proof_service(opener, base_url):
    email = f"phase6-proof-{time.time_ns()}@example.com"
    _response, signup_page, _duration = fetch(opener, base_url, "/signup")
    response, _content, _duration = fetch(
        opener,
        base_url,
        "/signup",
        {
            "csrf_token": csrf_token(signup_page),
            "first_name": "Phase",
            "last_name": "Six",
            "email": email,
            "password": PASSWORD,
        },
    )
    assert urlparse(response.geturl()).path == "/settings"

    _response, services_page, _duration = fetch(opener, base_url, "/services")
    response, _content, _duration = fetch(
        opener,
        base_url,
        "/services",
        {
            "csrf_token": csrf_token(services_page),
            "add_mode": "single",
            "service_date": "2026-01-04",
            "rite": "Renewed Ancient Text",
            "mode": "defaults",
        },
    )
    match = re.fullmatch(r"/service/(\d+)", urlparse(response.geturl()).path)
    if not match:
        raise AssertionError(f"Unexpected service redirect: {response.geturl()}")
    return int(match.group(1))


def cookie_header(cookie_jar):
    value = "; ".join(f"{cookie.name}={cookie.value}" for cookie in cookie_jar)
    if not value:
        raise AssertionError("Authenticated session cookie was not created")
    return value


def export_once(base_url, service_id, extension, cookie, output_path):
    opener = build_opener()
    response, content, duration_ms = fetch(
        opener,
        base_url,
        f"/service/{service_id}/export.{extension}",
        headers={"Cookie": cookie},
    )
    signatures = {"pdf": b"%PDF", "docx": b"PK\x03\x04"}
    assert response.status == 200
    assert content.startswith(signatures[extension])
    assert "attachment" in response.headers["Content-Disposition"]
    output_path.write_bytes(content)
    if extension == "docx":
        verify_docx(output_path)
    return {
        "bytes": len(content),
        "duration_ms": round(duration_ms, 1),
        "path": str(output_path),
    }


def verify_docx(path):
    required_parts = {
        "[Content_Types].xml",
        "word/document.xml",
        "word/styles.xml",
        "word/settings.xml",
    }
    with zipfile.ZipFile(path) as archive:
        missing = required_parts - set(archive.namelist())
        if missing:
            raise AssertionError(f"DOCX is missing required parts: {sorted(missing)}")
    document = Document(path)
    if not any(paragraph.text.strip() for paragraph in document.paragraphs):
        raise AssertionError("DOCX opened but contained no paragraph text")


def concurrent_exports(base_url, service_id, cookie, output_dir, label):
    jobs = [("pdf", 1), ("docx", 1)]
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = {
            f"{extension}_{number}": executor.submit(
                export_once,
                base_url,
                service_id,
                extension,
                cookie,
                output_dir / f"{label}-{extension}-{number}.{extension}",
            )
            for extension, number in jobs
        }
        return {name: future.result() for name, future in futures.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8787")
    parser.add_argument("--idle-seconds", type=float, default=70)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/phase6-proof"))
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    service_id = create_proof_service(opener, base_url)
    cookie = cookie_header(cookie_jar)

    warm = concurrent_exports(
        base_url, service_id, cookie, args.output_dir, "warm-concurrent"
    )
    time.sleep(args.idle_seconds)
    cold = concurrent_exports(
        base_url, service_id, cookie, args.output_dir, "cold-concurrent"
    )
    print(
        json.dumps(
            {
                "cold_after_idle_seconds": args.idle_seconds,
                "cold_concurrent": cold,
                "service_id": service_id,
                "warm_concurrent": warm,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
