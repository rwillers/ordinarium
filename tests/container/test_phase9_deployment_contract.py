import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
SCRIPTS = ROOT / "scripts" / "cloudflare"
sys.path.insert(0, str(SCRIPTS))


def _module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deployment_manifest = _module("deployment_manifest")
production_configs = _module("render_production_configs")
staging_verifier = _module("verify_staging_deployment")


COMMIT = "a" * 40
IMAGE_DIGESTS = {
    "ordinarium-web": "1" * 64,
    "ordinarium-documents": "2" * 64,
    "ordinarium-pco-jobs": "3" * 64,
    "ordinarium-email-jobs": "4" * 64,
}


def _deployment(identifier, version_id):
    return {
        "id": identifier,
        "versions": [{"version_id": version_id, "percentage": 100}],
    }


def _version(version_id):
    return {
        "id": version_id,
        "annotations": {
            "workers/tag": COMMIT,
            "workers/message": f"GitHub staging deployment {COMMIT}",
        },
    }


def _containers():
    return [
        {
            "name": name,
            "state": "ready",
            "image": (
                "registry.cloudflare.com/04d97a760786b6d5cc30242a4851976e/"
                f"{name}@sha256:{digest}"
            ),
        }
        for name, digest in IMAGE_DIGESTS.items()
    ]


def _manifest():
    return deployment_manifest.create_manifest(
        COMMIT,
        _deployment("app-deployment", "app-version"),
        _version("app-version"),
        _deployment("alert-deployment", "alert-version"),
        _version("alert-version"),
        _containers(),
        "12345",
    )


def test_pull_request_workflows_validate_without_deploying():
    workflow_names = ["ci.yml", "cloudflare-worker.yml", "container-images.yml"]
    workflows = [
        (ROOT / ".github" / "workflows" / name).read_text() for name in workflow_names
    ]

    assert all("pull_request:" in workflow for workflow in workflows)
    assert all("wrangler deploy" not in workflow for workflow in workflows)
    assert "Run D1 and container integration contracts" in workflows[0]
    assert "Run container integration smoke test" in workflows[2]


def test_staging_workflow_migrates_deploys_verifies_and_records_release():
    workflow = (
        ROOT / ".github" / "workflows" / "deploy-cloudflare-staging.yml"
    ).read_text()

    assert "push:" in workflow and "branches: [main]" in workflow
    assert "name: cloudflare-staging" in workflow
    assert "cancel-in-progress: false" in workflow
    assert workflow.index("Apply compatible D1 migrations") < workflow.index(
        "Deploy application and containers"
    )
    assert workflow.index("Verify staging Access credentials") < workflow.index(
        "Apply compatible D1 migrations"
    )
    assert workflow.index("Deploy alert classifier") < workflow.index(
        "Deploy application and containers"
    )
    assert "verify_staging_deployment.py" in workflow
    assert "staging-release-${{ github.sha }}" in workflow


def test_staging_access_preflight_checks_health_and_login(monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_ACCESS_CLIENT_ID", "client.access")
    monkeypatch.setenv("CLOUDFLARE_ACCESS_CLIENT_SECRET", "secret")
    paths = []

    class Headers:
        @staticmethod
        def get_content_type():
            return "text/html"

    def request(_base_url, path, _headers):
        paths.append(path)
        if path == "/health":
            return 200, Headers(), b'{"status": "ok"}'
        return 200, Headers(), b'<input name="csrf_token">'

    monkeypatch.setattr(staging_verifier, "_request", request)

    staging_verifier.verify_access("https://staging.example.com")

    assert paths == ["/health", "/login"]
    output = capsys.readouterr().out
    assert "client_secret(length=6, sha256=" in output
    assert "authenticated staging probes passed" in output


def test_staging_request_identifies_the_github_readiness_client(monkeypatch):
    observed = {}

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def read():
            return b"ok"

    def open_request(request, timeout):
        observed["user_agent"] = request.get_header("User-agent")
        observed["accept"] = request.get_header("Accept")
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr(staging_verifier, "urlopen", open_request)

    status, _headers, body = staging_verifier._request(
        "https://staging.example.com", "/health", {"X-Test": "value"}
    )

    assert (status, body) == (200, b"ok")
    assert observed == {
        "user_agent": staging_verifier.USER_AGENT,
        "accept": "application/json, text/html;q=0.9, */*;q=0.8",
        "timeout": 30,
    }


def test_staging_readiness_does_not_retry_access_rejection(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCESS_CLIENT_ID", "client.access")
    monkeypatch.setenv("CLOUDFLARE_ACCESS_CLIENT_SECRET", "secret")
    monkeypatch.setattr(staging_verifier, "_containers_ready", lambda *_args: True)
    monkeypatch.setattr(
        staging_verifier,
        "_request",
        lambda *_args: (_ for _ in ()).throw(
            staging_verifier.StagingRequestError(
                "/health", 403, "content-type=text/html; cf-ray=test"
            )
        ),
    )
    monkeypatch.setattr(
        staging_verifier.time,
        "sleep",
        lambda *_args: pytest.fail("non-retryable rejection slept"),
    )

    with pytest.raises(RuntimeError, match=r"/health returned HTTP 403"):
        staging_verifier.verify_staging(
            "https://staging.example.com", "wrangler", "config"
        )


def test_production_workflow_is_manual_disabled_and_exact_release_only():
    workflow = (
        ROOT / ".github" / "workflows" / "promote-cloudflare-production.yml"
    ).read_text()

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow and "push:" not in workflow
    assert "ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY == 'true'" in workflow
    assert "name: cloudflare-production" in workflow
    assert "git merge-base --is-ancestor" in workflow
    assert "deployment_manifest.py validate" in workflow
    assert "render_production_configs.py" in workflow
    assert "pinned container digests" in workflow


def test_release_manifest_requires_exact_worker_versions_and_image_digests():
    manifest = _manifest()

    assert manifest["commit_sha"] == COMMIT
    assert set(manifest["container_images"]) == set(IMAGE_DIGESTS)
    assert all("@sha256:" in image for image in manifest["container_images"].values())
    deployment_manifest.validate_manifest(manifest, COMMIT)

    manifest["container_images"][
        "ordinarium-web"
    ] = "registry.cloudflare.com/account/ordinarium-web:mutable"
    with pytest.raises(ValueError, match="not pinned by digest"):
        deployment_manifest.validate_manifest(manifest, COMMIT)


def test_production_renderer_uses_separate_resources_and_tested_images():
    app_source = json.loads((ROOT / "cloudflare" / "wrangler.jsonc").read_text())
    alert_source = json.loads(
        (ROOT / "cloudflare" / "wrangler.alerts.jsonc").read_text()
    )

    app, alerts = production_configs.render_configs(
        app_source,
        alert_source,
        _manifest(),
        "ordinarium.com",
        "production-database-id",
        "production-turnstile-site-key",
        "alerts@example.com",
    )

    assert app["name"] == "ordinarium-app-production"
    assert app["routes"] == [{"pattern": "ordinarium.com", "custom_domain": True}]
    assert app["d1_databases"][0]["database_name"] == "ordinarium-app-production"
    assert alerts["name"] == "ordinarium-alerts-production"
    assert all(
        container["name"].startswith("ordinarium-production-")
        for container in app["containers"]
    )
    assert all("@sha256:" in container["image"] for container in app["containers"])
    assert all(
        "image_build_context" not in container for container in app["containers"]
    )
    assert "ordinarium-app-staging-" not in json.dumps({"app": app, "alerts": alerts})
