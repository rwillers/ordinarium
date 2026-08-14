import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _config(name):
    return json.loads((ROOT / "cloudflare" / name).read_text())


def test_phase8_attaches_the_dedicated_tail_worker():
    app = _config("wrangler.jsonc")
    alerts = _config("wrangler.alerts.jsonc")

    assert app["tail_consumers"] == [{"service": "ordinarium-alerts-staging"}]
    assert alerts["name"] == "ordinarium-alerts-staging"
    assert alerts["main"] == "src/alert_tail.ts"
    assert alerts["queues"]["producers"] == [
        {
            "binding": "ALERTS_QUEUE",
            "queue": "ordinarium-app-staging-alerts",
        }
    ]
    assert alerts["durable_objects"]["bindings"] == [
        {
            "name": "ALERT_DEDUPLICATOR",
            "class_name": "AlertDeduplicator",
        }
    ]


def test_phase8_alert_recipient_and_provider_secret_stay_in_email_role():
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
    tail_source = (ROOT / "cloudflare" / "src" / "alert_tail.ts").read_text()

    assert "ALERT_EMAIL_TO" in email_block
    assert "MAILERSEND_API_TOKEN" in email_block
    assert "interceptHttps = true" in email_block
    assert (
        'REQUESTS_CA_BUNDLE: "/etc/cloudflare/certs/cloudflare-containers-ca.crt"'
        in email_block
    )
    assert '"api.mailersend.com": (request) => fetch(request)' in email_block
    assert "ALERT_EMAIL_TO" not in web_block
    assert "ALERT_EMAIL_TO" not in document_block
    assert "ALERT_EMAIL_TO" not in pco_block
    assert "MAILERSEND" not in tail_source
    assert _config("wrangler.jsonc")["vars"]["ALERT_EMAIL_TO"] == (
        "ryanwillers+ordo@gmail.com"
    )


def test_web_container_has_explicit_turnstile_https_egress():
    worker_source = (ROOT / "cloudflare" / "src" / "index.ts").read_text()
    web_block = worker_source.split("export class WebContainer", 1)[1].split(
        "export class DocumentContainer", 1
    )[0]

    assert "interceptHttps = true" in web_block
    assert '"challenges.cloudflare.com"' in web_block
    assert (
        'SSL_CERT_FILE: "/etc/cloudflare/certs/cloudflare-containers-ca.crt"'
        in web_block
    )
    assert (
        'REQUESTS_CA_BUNDLE: "/etc/cloudflare/certs/cloudflare-containers-ca.crt"'
        in web_block
    )
    assert (
        '"challenges.cloudflare.com": (request, environment: Cloudflare.Env)'
        in web_block
    )
    assert "handleTurnstileRequest(request, environment)" in web_block
    assert (
        'TURNSTILE_SECRET_KEY: env.TURNSTILE_SECRET_KEY ? "worker-managed" : ""'
        in web_block
    )


def test_pco_jobs_container_has_explicit_planning_center_https_egress():
    worker_source = (ROOT / "cloudflare" / "src" / "index.ts").read_text()
    pco_block = worker_source.split("export class PcoJobsContainer", 1)[1].split(
        "export class EmailJobsContainer", 1
    )[0]

    assert "enableInternet = false" in pco_block
    assert "interceptHttps = true" in pco_block
    assert '"api.planningcenteronline.com"' in pco_block
    assert (
        'REQUESTS_CA_BUNDLE: "/etc/cloudflare/certs/cloudflare-containers-ca.crt"'
        in pco_block
    )
    assert (
        '"api.planningcenteronline.com": (request) => fetch(request)'
        in pco_block
    )
