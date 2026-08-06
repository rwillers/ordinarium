#!/usr/bin/env python3
"""Build, push, and pin the exact container images for a staging release."""

import argparse
import copy
import json
import re
import subprocess
from pathlib import Path


IMAGE_PATTERN = re.compile(
    r"registry\.cloudflare\.com/[0-9a-f]+/[a-z0-9-]+@sha256:[0-9a-f]{64}"
)
DOCKERFILES = {
    "ordinarium-web": "containers/web/Dockerfile",
    "ordinarium-documents": "containers/documents/Dockerfile",
    "ordinarium-pco-jobs": "containers/jobs/Dockerfile",
    "ordinarium-email-jobs": "containers/jobs/Dockerfile",
}


def _run(command, cwd, capture_output=False):
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=capture_output,
        text=True,
    )


def _digest_reference(repo_digests, repository):
    prefix = f"{repository}@sha256:"
    matches = sorted(item for item in repo_digests if item.startswith(prefix))
    if len(matches) != 1 or not IMAGE_PATTERN.fullmatch(matches[0]):
        raise RuntimeError(
            f"expected one immutable digest for {repository}, found {matches!r}"
        )
    return matches[0]


def build_and_push_image(
    repository_root, wrangler, config, account_id, name, tag, dockerfile
):
    local_image = f"{name}:{tag}"
    registry_repository = f"registry.cloudflare.com/{account_id}/{name}"
    registry_image = f"{registry_repository}:{tag}"
    _run(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "--file",
            str(repository_root / dockerfile),
            "--tag",
            local_image,
            str(repository_root),
        ],
        repository_root,
    )
    _run(
        [wrangler, "containers", "push", local_image, "--config", str(config)],
        repository_root,
    )
    result = _run(
        [
            "docker",
            "image",
            "inspect",
            registry_image,
            "--format",
            "{{json .RepoDigests}}",
        ],
        repository_root,
        capture_output=True,
    )
    return _digest_reference(json.loads(result.stdout), registry_repository)


def render_pinned_config(source, images):
    rendered = copy.deepcopy(source)
    configured_names = {container["name"] for container in rendered["containers"]}
    if configured_names != set(images):
        raise ValueError("release images do not match the configured container set")
    for container in rendered["containers"]:
        container["image"] = images[container["name"]]
        container.pop("image_build_context", None)
    return rendered


def prepare_release(
    repository_root,
    source_config,
    output_config,
    output_images,
    wrangler,
    account_id,
    tag,
):
    images = {
        name: build_and_push_image(
            repository_root,
            wrangler,
            source_config,
            account_id,
            name,
            tag,
            dockerfile,
        )
        for name, dockerfile in DOCKERFILES.items()
    }
    source = json.loads(source_config.read_text())
    rendered = render_pinned_config(source, images)
    output_config.write_text(json.dumps(rendered, indent=2) + "\n")
    output_images.write_text(json.dumps(images, indent=2, sort_keys=True) + "\n")


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--source-config", type=Path, required=True)
    parser.add_argument("--output-config", type=Path, required=True)
    parser.add_argument("--output-images", type=Path, required=True)
    parser.add_argument("--wrangler", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    prepare_release(
        args.repository_root.resolve(),
        args.source_config.resolve(),
        args.output_config.resolve(),
        args.output_images.resolve(),
        str(Path(args.wrangler).resolve()),
        args.account_id,
        args.tag,
    )


if __name__ == "__main__":
    _main()
