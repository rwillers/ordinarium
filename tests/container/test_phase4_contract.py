import json
from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_worker_exposes_only_private_d1_bridge_to_web_container():
    worker = (ROOT / "cloudflare/src/index.ts").read_text()
    bridge = (ROOT / "cloudflare/src/d1_bridge.ts").read_text()

    assert '"d1.internal"' in worker
    assert "handleD1Request(request, environment.APP_DB)" in worker
    assert 'request.method !== "POST"' in bridge
    assert 'case "fetch_one"' in bridge
    assert 'case "fetch_all"' in bridge
    assert 'case "execute"' in bridge
    assert 'case "batch"' in bridge
    assert 'case "allocate_id"' in bridge


def test_worker_binds_only_fresh_staging_d1_database():
    config = json.loads((ROOT / "cloudflare/wrangler.jsonc").read_text())

    assert config["d1_databases"] == [
        {
            "binding": "APP_DB",
            "database_name": "ordinarium-app-staging",
            "database_id": "e13336d8-cf7c-4c63-955d-4d8c7cfa4321",
            "migrations_dir": "../migrations/d1",
        }
    ]
