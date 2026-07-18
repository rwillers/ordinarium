#!/usr/bin/env python3
import argparse
import difflib
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ordinarium import create_app


PATHS = ("/", "/login", "/signup", "/reset-password")
CSRF_META_PATTERN = re.compile(r'(<meta name="csrf-token" content=")[^"]*(">)')
CSRF_INPUT_PATTERN = re.compile(
    r'(<input type="hidden" name="csrf_token" value=")[^"]*(">)'
)
TURNSTILE_SITE_KEY_PATTERN = re.compile(r'(sitekey:\s*")[^"]*(")')


def main():
    parser = argparse.ArgumentParser(
        description="Compare public Flask HTML with the untouched AWS deployment."
    )
    parser.add_argument(
        "--aws-base-url",
        default="https://www.ordinarium.com",
    )
    args = parser.parse_args()

    session = requests.Session()
    aws_pages = {
        path: _fetch(session, f"{args.aws_base_url.rstrip('/')}{path}")
        for path in PATHS
    }
    turnstile_site_key = _turnstile_site_key(aws_pages["/login"])

    app = create_app()
    app.config.update(
        TESTING=True,
        SECRET_KEY="phase5-html-comparison",
        WTF_CSRF_ENABLED=True,
        TURNSTILE_ENABLED=bool(turnstile_site_key),
        TURNSTILE_SITE_KEY=turnstile_site_key,
        TURNSTILE_SECRET_KEY="comparison-only",
    )
    client = app.test_client()

    mismatches = []
    for path, aws_html in aws_pages.items():
        local_response = client.get(path)
        if local_response.status_code != 200:
            mismatches.append(f"{path}: local HTTP {local_response.status_code}")
            continue
        normalized_aws = normalize_html(aws_html)
        normalized_local = normalize_html(local_response.get_data(as_text=True))
        if normalized_aws != normalized_local:
            diff = "".join(
                difflib.unified_diff(
                    normalized_aws.splitlines(keepends=True),
                    normalized_local.splitlines(keepends=True),
                    fromfile=f"aws{path}",
                    tofile=f"local{path}",
                    n=2,
                )
            )
            mismatches.append(diff)

    if mismatches:
        print("\n".join(mismatches))
        raise SystemExit(1)
    print(f"Matched {len(PATHS)} normalized public HTML snapshots against AWS.")


def normalize_html(value):
    value = value.replace("\r\n", "\n")
    value = CSRF_META_PATTERN.sub(r"\1<csrf-token>\2", value)
    value = CSRF_INPUT_PATTERN.sub(r"\1<csrf-token>\2", value)
    value = TURNSTILE_SITE_KEY_PATTERN.sub(r"\1<turnstile-site-key>\2", value)
    return value


def _fetch(session, url):
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def _turnstile_site_key(html):
    match = TURNSTILE_SITE_KEY_PATTERN.search(html)
    return match.group(0).split('"', 2)[1] if match else None


if __name__ == "__main__":
    main()
