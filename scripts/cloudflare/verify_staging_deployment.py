#!/usr/bin/env python3
"""Run side-effect-free readiness checks against Cloudflare staging."""

import argparse
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


def _access_headers():
    client_id = os.environ.get("CLOUDFLARE_ACCESS_CLIENT_ID")
    client_secret = os.environ.get("CLOUDFLARE_ACCESS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Cloudflare Access service-token credentials are required")
    return {
        "CF-Access-Client-Id": client_id,
        "CF-Access-Client-Secret": client_secret,
    }


def _request(base_url, path, headers):
    request = Request(f"{base_url.rstrip('/')}{path}", headers=headers)
    with urlopen(request, timeout=30) as response:
        return response.status, response.headers, response.read()


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
    last_error = None
    for _attempt in range(attempts):
        try:
            if not _containers_ready(wrangler, config):
                raise RuntimeError("container rollout is not ready")

            status, _headers, body = _request(base_url, "/health", headers)
            if status != 200 or json.loads(body) != {"status": "ok"}:
                raise RuntimeError("edge health response is not ready")

            status, response_headers, body = _request(base_url, "/login", headers)
            content_type = response_headers.get_content_type()
            if status != 200 or content_type != "text/html":
                raise RuntimeError("web container login route is not ready")
            if b'name="csrf_token"' not in body:
                raise RuntimeError("web container login form is incomplete")
            return
        except (
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
            RuntimeError,
            subprocess.CalledProcessError,
        ) as error:
            last_error = error
            time.sleep(10)
    raise RuntimeError(f"staging readiness checks did not pass: {last_error}")


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--wrangler", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    verify_staging(args.base_url, args.wrangler, args.config)
    print("Staging edge, container, and login readiness checks passed.")


if __name__ == "__main__":
    _main()
