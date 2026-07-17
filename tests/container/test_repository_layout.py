import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[2]
CONTAINER_ROLES = ("web", "documents", "jobs")
BASE_IMAGE = (
    "python:3.13.14-slim-bookworm@"
    "sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64"
)


def test_required_phase_two_layout_exists():
    required_paths = (
        "cloudflare/src/index.ts",
        "cloudflare/wrangler.jsonc",
        "containers/web/Dockerfile",
        "containers/documents/Dockerfile",
        "containers/jobs/Dockerfile",
        "container_role_apps.py",
        "ordinarium/infrastructure/__init__.py",
        "migrations/d1/README.md",
        "scripts/cloudflare/verify_phase2_images.sh",
    )

    for relative_path in required_paths:
        assert (REPOSITORY_ROOT / relative_path).is_file(), relative_path


def test_container_images_share_hardened_runtime_contract():
    for role in CONTAINER_ROLES:
        content = (REPOSITORY_ROOT / "containers" / role / "Dockerfile").read_text()

        assert f"FROM {BASE_IMAGE}" in content
        assert "USER ordinarium" in content
        assert "EXPOSE 8080" in content
        assert "STOPSIGNAL SIGTERM" in content
        assert "HEALTHCHECK" in content
        assert "--require-hashes" in content


def test_role_dependencies_are_isolated():
    requirements = {
        role: (REPOSITORY_ROOT / "containers" / "requirements" / f"{role}.in")
        .read_text()
        .lower()
        for role in CONTAINER_ROLES
    }

    assert "weasyprint" not in requirements["web"]
    assert "python-docx" not in requirements["web"]
    assert "weasyprint" in requirements["documents"]
    assert "python-docx" in requirements["documents"]
    assert "cryptography" in requirements["jobs"]
    assert "httpx" in requirements["jobs"]
    assert "weasyprint" not in requirements["jobs"]
    assert "python-docx" not in requirements["jobs"]


def test_wrangler_config_matches_target_sizing():
    config = json.loads((REPOSITORY_ROOT / "cloudflare" / "wrangler.jsonc").read_text())
    containers = {item["class_name"]: item for item in config["containers"]}

    assert containers["WebContainer"]["instance_type"] == "basic"
    assert containers["WebContainer"]["max_instances"] == 1
    assert containers["DocumentContainer"]["instance_type"] == "standard-1"
    assert containers["DocumentContainer"]["max_instances"] == 2
    assert containers["PcoJobsContainer"]["max_instances"] == 1
    assert containers["EmailJobsContainer"]["max_instances"] == 2
    assert all(item["image_build_context"] == ".." for item in containers.values())
