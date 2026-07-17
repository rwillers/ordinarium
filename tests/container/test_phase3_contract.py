from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_worker_routes_to_named_web_and_document_containers():
    worker = (ROOT / "cloudflare/src/index.ts").read_text()

    assert "getByName(WEB_INSTANCE_NAME)" in worker
    assert '"documents.internal"' in worker
    assert "getByName(\n      DOCUMENT_INSTANCE_NAME" in worker
    assert "ContainerProxy" in worker


def test_staging_has_one_access_protectable_origin():
    config = (ROOT / "cloudflare/wrangler.jsonc").read_text()

    assert '"workers_dev": false' in config
    assert '"pattern": "containers-staging.ordinarium.com"' in config
    assert '"custom_domain": true' in config


def test_web_proof_marks_sqlite_as_disposable():
    worker = (ROOT / "cloudflare/src/index.ts").read_text()
    startup = (ROOT / "scripts/cloudflare/start_web_proof.sh").read_text()

    assert 'ORDINARIUM_DISPOSABLE_SQLITE: "true"' in worker
    assert "flask --app ordinarium init-db" in startup
