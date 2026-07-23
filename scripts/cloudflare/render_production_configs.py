#!/usr/bin/env python3
"""Render production Wrangler configs from a tested staging manifest."""

import argparse
import copy
import json
from pathlib import Path

from deployment_manifest import validate_manifest


CONTAINER_NAMES = {
    "WebContainer": ("ordinarium-web", "ordinarium-production-web"),
    "DocumentContainer": (
        "ordinarium-documents",
        "ordinarium-production-documents",
    ),
    "PcoJobsContainer": ("ordinarium-pco-jobs", "ordinarium-production-pco-jobs"),
    "EmailJobsContainer": (
        "ordinarium-email-jobs",
        "ordinarium-production-email-jobs",
    ),
}


def _replace_staging_queue_names(value):
    if isinstance(value, str):
        return value.replace("ordinarium-app-staging-", "ordinarium-app-production-")
    if isinstance(value, list):
        return [_replace_staging_queue_names(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace_staging_queue_names(item) for key, item in value.items()}
    return value


def render_configs(
    app_source,
    alert_source,
    manifest,
    domain,
    database_id,
    turnstile_site_key,
    alert_email,
):
    validate_manifest(manifest, manifest.get("commit_sha"))
    if not domain or "/" in domain:
        raise ValueError("production domain must be a hostname")
    if not database_id:
        raise ValueError("production D1 database ID is required")

    app = _replace_staging_queue_names(copy.deepcopy(app_source))
    app["name"] = "ordinarium-app-production"
    app["routes"] = [{"pattern": domain, "custom_domain": True}]
    app["tail_consumers"] = [{"service": "ordinarium-alerts-production"}]
    app["vars"].update(
        {
            "DEPLOYMENT_ENV": "production",
            "APP_ORIGIN": f"https://{domain}",
            "SIDE_EFFECTS_HOSTNAME": domain,
            "EXTERNAL_SIDE_EFFECTS_ENABLED": "true",
            "TURNSTILE_SITE_KEY": turnstile_site_key,
            "TURNSTILE_EXPECTED_HOSTNAME": domain,
            "ALERT_EMAIL_TO": alert_email,
        }
    )
    app["d1_databases"][0].update(
        {
            "database_name": "ordinarium-app-production",
            "database_id": database_id,
        }
    )

    images = manifest["container_images"]
    for container in app["containers"]:
        source_name, production_name = CONTAINER_NAMES[container["class_name"]]
        container["name"] = production_name
        container["image"] = images[source_name]
        container.pop("image_build_context", None)

    alerts = _replace_staging_queue_names(copy.deepcopy(alert_source))
    alerts["name"] = "ordinarium-alerts-production"
    return app, alerts


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-source", required=True)
    parser.add_argument("--alerts-source", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--database-id", required=True)
    parser.add_argument("--turnstile-site-key", required=True)
    parser.add_argument("--alert-email", required=True)
    parser.add_argument("--app-output", required=True)
    parser.add_argument("--alerts-output", required=True)
    args = parser.parse_args()

    app, alerts = render_configs(
        json.loads(Path(args.app_source).read_text()),
        json.loads(Path(args.alerts_source).read_text()),
        json.loads(Path(args.manifest).read_text()),
        args.domain,
        args.database_id,
        args.turnstile_site_key,
        args.alert_email,
    )
    Path(args.app_output).write_text(json.dumps(app, indent=2) + "\n")
    Path(args.alerts_output).write_text(json.dumps(alerts, indent=2) + "\n")


if __name__ == "__main__":
    _main()
