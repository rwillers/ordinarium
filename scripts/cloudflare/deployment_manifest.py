#!/usr/bin/env python3
"""Create and validate immutable Cloudflare deployment manifests."""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
IMAGE_PATTERN = re.compile(
    r"registry\.cloudflare\.com/[0-9a-f]+/[a-z0-9-]+@sha256:[0-9a-f]{64}"
)
EXPECTED_CONTAINERS = {
    "ordinarium-web",
    "ordinarium-documents",
    "ordinarium-pco-jobs",
    "ordinarium-email-jobs",
}


def _read_json(path):
    return json.loads(Path(path).read_text())


def _active_version(deployment, version):
    versions = deployment.get("versions", [])
    if len(versions) != 1 or versions[0].get("percentage") != 100:
        raise ValueError("deployment must have exactly one version at 100 percent")
    version_id = versions[0].get("version_id")
    if version_id != version.get("id"):
        raise ValueError("deployment and version metadata do not match")
    return version_id


def _verify_commit_annotation(version, commit_sha):
    annotations = version.get("annotations", {})
    if annotations.get("workers/tag") != commit_sha:
        raise ValueError("Worker version is not tagged with the deployment commit")
    if commit_sha not in annotations.get("workers/message", ""):
        raise ValueError(
            "Worker version message does not identify the deployment commit"
        )


def create_manifest(
    commit_sha,
    app_deployment,
    app_version,
    alert_deployment,
    alert_version,
    containers,
    workflow_run_id=None,
):
    if not COMMIT_PATTERN.fullmatch(commit_sha):
        raise ValueError("commit SHA must contain 40 lowercase hexadecimal characters")

    app_version_id = _active_version(app_deployment, app_version)
    alert_version_id = _active_version(alert_deployment, alert_version)
    _verify_commit_annotation(app_version, commit_sha)
    _verify_commit_annotation(alert_version, commit_sha)

    images = {}
    for container in containers:
        name = container.get("name")
        if name not in EXPECTED_CONTAINERS:
            continue
        image = container.get("image", "")
        if not IMAGE_PATTERN.fullmatch(image):
            raise ValueError(
                f"container {name} does not expose an immutable image digest"
            )
        state = container.get("state")
        if state not in {"active", "ready"}:
            raise ValueError(f"container {name} is not ready (state={state!r})")
        images[name] = image

    if set(images) != EXPECTED_CONTAINERS:
        missing = sorted(EXPECTED_CONTAINERS - set(images))
        raise ValueError(
            f"deployment metadata is missing containers: {', '.join(missing)}"
        )

    return {
        "schema_version": 1,
        "environment": "staging",
        "commit_sha": commit_sha,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "github_workflow_run_id": workflow_run_id,
        "workers": {
            "application": {
                "name": "ordinarium-app-staging",
                "deployment_id": app_deployment.get("id"),
                "version_id": app_version_id,
            },
            "alerts": {
                "name": "ordinarium-alerts-staging",
                "deployment_id": alert_deployment.get("id"),
                "version_id": alert_version_id,
            },
        },
        "container_images": dict(sorted(images.items())),
    }


def validate_manifest(manifest, expected_commit=None):
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported deployment manifest schema")
    if manifest.get("environment") != "staging":
        raise ValueError("only a staging deployment can be promoted")

    commit_sha = manifest.get("commit_sha", "")
    if not COMMIT_PATTERN.fullmatch(commit_sha):
        raise ValueError("deployment manifest has an invalid commit SHA")
    if expected_commit and commit_sha != expected_commit:
        raise ValueError("deployment manifest commit does not match promotion input")

    workers = manifest.get("workers", {})
    for role in ("application", "alerts"):
        worker = workers.get(role, {})
        if not worker.get("deployment_id") or not worker.get("version_id"):
            raise ValueError(f"deployment manifest is missing {role} Worker metadata")

    images = manifest.get("container_images", {})
    if set(images) != EXPECTED_CONTAINERS:
        raise ValueError("deployment manifest does not contain the exact container set")
    for name, image in images.items():
        if not IMAGE_PATTERN.fullmatch(image):
            raise ValueError(f"container {name} is not pinned by digest")
    return manifest


def _capture(args):
    manifest = create_manifest(
        args.commit,
        _read_json(args.app_deployment),
        _read_json(args.app_version),
        _read_json(args.alert_deployment),
        _read_json(args.alert_version),
        _read_json(args.containers),
        args.workflow_run_id,
    )
    Path(args.output).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _validate(args):
    validate_manifest(_read_json(args.manifest), args.commit)


def _parser():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    capture = commands.add_parser("capture")
    capture.add_argument("--commit", required=True)
    capture.add_argument("--app-deployment", required=True)
    capture.add_argument("--app-version", required=True)
    capture.add_argument("--alert-deployment", required=True)
    capture.add_argument("--alert-version", required=True)
    capture.add_argument("--containers", required=True)
    capture.add_argument("--workflow-run-id")
    capture.add_argument("--output", required=True)
    capture.set_defaults(handler=_capture)

    validate = commands.add_parser("validate")
    validate.add_argument("--manifest", required=True)
    validate.add_argument("--commit", required=True)
    validate.set_defaults(handler=_validate)
    return parser


if __name__ == "__main__":
    parsed = _parser().parse_args()
    parsed.handler(parsed)
