#!/usr/bin/env python3
"""Run side-effect-free readiness checks against Cloudflare staging."""

import argparse
import hashlib
import json
import os
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


EXPECTED_CONTAINERS = {
    "ordinarium-web",
    "ordinarium-documents",
    "ordinarium-pco-jobs",
    "ordinarium-email-jobs",
}
USER_AGENT = "Ordinarium-GitHub-Staging-Readiness/1.0"


class StagingRequestError(RuntimeError):
    """An HTTP response that did not reach a staging readiness endpoint."""

    def __init__(self, path, status, details):
        self.path = path
        self.status = status
        super().__init__(f"request {path} returned HTTP {status}: {details}")


def _access_headers():
    client_id = os.environ.get("CLOUDFLARE_ACCESS_CLIENT_ID")
    client_secret = os.environ.get("CLOUDFLARE_ACCESS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Cloudflare Access service-token credentials are required")
    return {
        "CF-Access-Client-Id": client_id,
        "CF-Access-Client-Secret": client_secret,
    }


def _credential_metadata(headers):
    def describe(value):
        fingerprint = hashlib.sha256(value.encode()).hexdigest()[:12]
        return f"length={len(value)}, sha256={fingerprint}"

    return (
        "Cloudflare Access credential metadata: "
        f"client_id({describe(headers['CF-Access-Client-Id'])}); "
        f"client_secret({describe(headers['CF-Access-Client-Secret'])})"
    )


def _error_details(error):
    body = error.read(512).decode("utf-8", errors="replace")
    body = " ".join(body.split())
    details = [f"content-type={error.headers.get('Content-Type', 'unknown')}"]
    for header in ("CF-Ray", "Location"):
        if value := error.headers.get(header):
            details.append(f"{header.lower()}={value}")
    if body:
        details.append(f"body={body[:240]}")
    return "; ".join(details)


def _request(base_url, path, headers):
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        headers={
            **headers,
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, response.headers, response.read()
    except HTTPError as error:
        raise StagingRequestError(path, error.code, _error_details(error)) from error


def _verify_edge_routes(base_url, headers):
    status, _headers, body = _request(base_url, "/health", headers)
    if status != 200 or json.loads(body) != {"status": "ok"}:
        raise RuntimeError("edge health response is not ready")

    status, response_headers, body = _request(base_url, "/login", headers)
    content_type = response_headers.get_content_type()
    if status != 200 or content_type != "text/html":
        raise RuntimeError("web container login route is not ready")
    if b'name="csrf_token"' not in body:
        raise RuntimeError("web container login form is incomplete")


def verify_access(base_url):
    headers = _access_headers()
    print(_credential_metadata(headers))
    _verify_edge_routes(base_url, headers)
    print("Cloudflare Access authenticated staging probes passed.")


def _containers_ready(wrangler, config):
    result = subprocess.run(
        [wrangler, "containers", "list", "--json", "--config", config],
        check=True,
        capture_output=True,
        text=True,
    )
    containers = {
        item.get("name"): item
        for item in json.loads(result.stdout)
        if item.get("name") in EXPECTED_CONTAINERS
    }
    if set(containers) != EXPECTED_CONTAINERS:
        return False
    return all(item.get("state") in {"active", "ready"} for item in containers.values())


def verify_staging(base_url, wrangler, config, attempts=60):
    headers = _access_headers()
    print(_credential_metadata(headers))
    last_error = None
    for _attempt in range(attempts):
        try:
            if not _containers_ready(wrangler, config):
                raise RuntimeError("container rollout is not ready")
            _verify_edge_routes(base_url, headers)
            return
        except (
            URLError,
            TimeoutError,
            json.JSONDecodeError,
            RuntimeError,
            subprocess.CalledProcessError,
        ) as error:
            last_error = error
            if (
                isinstance(error, StagingRequestError)
                and 400 <= error.status < 500
                and error.status not in {408, 429}
            ):
                raise RuntimeError(
                    f"staging readiness failed without retry: {error}"
                ) from error
            time.sleep(10)
    raise RuntimeError(f"staging readiness checks did not pass: {last_error}")


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--wrangler")
    parser.add_argument("--config")
    parser.add_argument("--access-preflight", action="store_true")
    args = parser.parse_args()
    if args.access_preflight:
        verify_access(args.base_url)
        return
    if not args.wrangler or not args.config:
        parser.error("--wrangler and --config are required for readiness verification")
    verify_staging(args.base_url, args.wrangler, args.config)
    print("Staging edge, container, and login readiness checks passed.")


if __name__ == "__main__":
    _main()
