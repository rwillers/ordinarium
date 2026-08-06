from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_worker_routes_to_named_web_and_document_containers():
    worker = (ROOT / "cloudflare/src/index.ts").read_text()
    orchestrator = (ROOT / "cloudflare/src/document_orchestrator.ts").read_text()

    assert "getByName(WEB_INSTANCE_NAME)" in worker
    assert '"documents.internal"' in worker
    assert "handleDocumentRequest(request, environment)" in worker
    assert '"staging-documents-0"' in orchestrator
    assert '"staging-documents-1"' in orchestrator
    assert '"X-Ordinarium-Document-Auth"' in orchestrator
    assert "ContainerProxy" in worker


def test_staging_has_one_access_protectable_origin():
    config = (ROOT / "cloudflare/wrangler.jsonc").read_text()

    assert '"workers_dev": false' in config
    assert '"pattern": "staging.ordinarium.com"' in config
    assert '"custom_domain": true' in config


def test_web_startup_is_optimized_for_d1():
    worker = (ROOT / "cloudflare/src/index.ts").read_text()
    startup = (ROOT / "scripts/cloudflare/start_web_proof.sh").read_text()
    dockerfile = (ROOT / "containers/web/Dockerfile").read_text()

    assert "ORDINARIUM_DISPOSABLE_SQLITE" not in worker
    assert "init-db" not in startup
    assert "--preload" in startup
    assert "python -m compileall -q /app/ordinarium /app/app.py" in dockerfile
    assert "--timeout=125" in startup


def test_web_container_disables_access_logging_for_token_bearing_routes():
    startup = (ROOT / "scripts/cloudflare/start_web_proof.sh").read_text()
    reset_routes = (ROOT / "ordinarium/password_reset_routes.py").read_text()

    assert '@bp.route("/reset-password/<token>"' in reset_routes
    # Gunicorn access logging is disabled by default. Configuring neither an
    # access destination nor format prevents the bearer token path from being
    # emitted while the dedicated error log remains available.
    assert "--access-logfile" not in startup
    assert "--access-logformat" not in startup
    assert "--error-logfile=-" in startup
