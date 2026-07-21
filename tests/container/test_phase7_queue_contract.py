import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _wrangler_config():
    return json.loads((ROOT / "cloudflare" / "wrangler.jsonc").read_text())


def test_phase7_declares_exact_staging_queues_and_dlqs():
    queues = _wrangler_config()["queues"]

    assert queues["producers"] == [
        {
            "binding": "PCO_JOBS_QUEUE",
            "queue": "ordinarium-app-staging-pco-jobs",
        },
        {
            "binding": "EMAIL_JOBS_QUEUE",
            "queue": "ordinarium-app-staging-email-jobs",
        },
        {
            "binding": "PCO_JOBS_DLQ",
            "queue": "ordinarium-app-staging-pco-jobs-dlq",
        },
        {
            "binding": "EMAIL_JOBS_DLQ",
            "queue": "ordinarium-app-staging-email-jobs-dlq",
        },
    ]
    assert {consumer["queue"] for consumer in queues["consumers"]} == {
        "ordinarium-app-staging-pco-jobs",
        "ordinarium-app-staging-pco-jobs-dlq",
        "ordinarium-app-staging-email-jobs",
        "ordinarium-app-staging-email-jobs-dlq",
        "ordinarium-app-staging-alerts",
        "ordinarium-app-staging-alerts-dlq",
    }


def test_phase7_pco_queue_is_strictly_serial_and_both_primaries_have_dlqs():
    consumers = {
        consumer["queue"]: consumer
        for consumer in _wrangler_config()["queues"]["consumers"]
    }
    pco = consumers["ordinarium-app-staging-pco-jobs"]
    email = consumers["ordinarium-app-staging-email-jobs"]

    assert pco["max_batch_size"] == 1
    assert pco["max_concurrency"] == 1
    assert pco["dead_letter_queue"] == "ordinarium-app-staging-pco-jobs-dlq"
    assert email["max_batch_size"] == 1
    assert email["max_concurrency"] == 2
    assert email["dead_letter_queue"] == "ordinarium-app-staging-email-jobs-dlq"
    assert consumers["ordinarium-app-staging-pco-jobs-dlq"]["max_retries"] == 100
    assert consumers["ordinarium-app-staging-email-jobs-dlq"]["max_retries"] == 100
    assert consumers["ordinarium-app-staging-alerts"]["dead_letter_queue"] == (
        "ordinarium-app-staging-alerts-dlq"
    )
    assert consumers["ordinarium-app-staging-alerts-dlq"]["max_retries"] == 100


def test_phase7_documents_finite_dlq_retries_and_reconciliation_fallback():
    operations = (ROOT / "cloudflare" / "PHASE7_QUEUE_OPERATIONS.md").read_text()

    assert "100 delivery retries" in operations
    assert "scheduled D1 reconciliation" in operations
    assert "cannot guarantee terminalization" in operations


def test_phase7_worker_ci_runs_behavior_tests():
    workflow = (ROOT / ".github" / "workflows" / "cloudflare-worker.yml").read_text()

    assert "run: npm run typecheck" in workflow
    assert "run: npm test" in workflow


def test_phase7_container_secrets_are_role_isolated():
    worker_source = (ROOT / "cloudflare" / "src" / "index.ts").read_text()
    web_block = worker_source.split("export class WebContainer", 1)[1].split(
        "export class DocumentContainer", 1
    )[0]
    document_block = worker_source.split("export class DocumentContainer", 1)[1].split(
        "export class PcoJobsContainer", 1
    )[0]
    pco_block = worker_source.split("export class PcoJobsContainer", 1)[1].split(
        "export class EmailJobsContainer", 1
    )[0]
    email_block = worker_source.split("export class EmailJobsContainer", 1)[1].split(
        "const worker", 1
    )[0]

    assert "PCO_TOKEN_ENCRYPTION_KEYS" in pco_block
    assert "PCO_CLIENT_SECRET" in pco_block
    assert "MAILERSEND_API_TOKEN" not in pco_block
    assert "MAILERSEND_API_TOKEN" in email_block
    assert "PASSWORD_RESET_DELIVERY_KEY" in email_block
    assert "PCO_TOKEN_ENCRYPTION_KEYS" not in email_block
    assert '"d1.internal"' in pco_block
    assert '"d1.internal"' in email_block
    assert "PCO_CLIENT_ID" in web_block
    assert "PCO_CLIENT_SECRET" in web_block
    assert "PCO_CLIENT_SECRET" not in document_block
    assert "PCO_CLIENT_SECRET" not in email_block
