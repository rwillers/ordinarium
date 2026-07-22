import json
from urllib.error import URLError

from ordinarium import turnstile


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def configure_turnstile(app):
    app.config.update(
        TURNSTILE_ENABLED=True,
        TURNSTILE_SITE_KEY="public-site-key",
        TURNSTILE_SECRET_KEY="private-secret-key",
        TURNSTILE_EXPECTED_HOSTNAME="containers-staging.ordinarium.com",
    )


def test_turnstile_accepts_matching_hostname_and_action(app, monkeypatch):
    configure_turnstile(app)
    monkeypatch.setattr(
        turnstile.urlrequest,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {
                "success": True,
                "hostname": "containers-staging.ordinarium.com",
                "action": "login",
            }
        ),
    )

    with app.app_context():
        assert turnstile.verify_turnstile_response(
            "token", expected_action="login"
        ) == (True, None)


def test_turnstile_rejects_hostname_or_action_mismatch(app, monkeypatch):
    configure_turnstile(app)
    payload = {
        "success": True,
        "hostname": "unexpected.example",
        "action": "login",
    }
    monkeypatch.setattr(
        turnstile.urlrequest,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(payload),
    )

    with app.app_context():
        assert turnstile.verify_turnstile_response(
            "token", expected_action="login"
        ) == (False, "hostname-mismatch")
        payload["hostname"] = "containers-staging.ordinarium.com"
        payload["action"] = "signup"
        assert turnstile.verify_turnstile_response(
            "token", expected_action="login"
        ) == (False, "action-mismatch")


def test_turnstile_submits_secret_token_and_remote_ip(app, monkeypatch):
    configure_turnstile(app)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = request.data.decode("utf-8")
        return FakeResponse(
            {
                "success": True,
                "hostname": "containers-staging.ordinarium.com",
                "action": "signup",
            }
        )

    monkeypatch.setattr(turnstile.urlrequest, "urlopen", fake_urlopen)

    with app.app_context():
        assert turnstile.verify_turnstile_response(
            "response-token", "203.0.113.8", expected_action="signup"
        ) == (True, None)

    assert captured == {
        "url": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        "timeout": 5,
        "body": (
            "secret=private-secret-key&response=response-token&remoteip=203.0.113.8"
        ),
    }


def test_turnstile_reports_transport_and_upstream_rejections(app, monkeypatch):
    configure_turnstile(app)

    monkeypatch.setattr(
        turnstile.urlrequest,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("unreachable")),
    )
    with app.app_context():
        assert turnstile.verify_turnstile_response("token") == (
            False,
            "verification-error",
        )

    monkeypatch.setattr(
        turnstile.urlrequest,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {"success": False, "error-codes": ["invalid-input-response"]}
        ),
    )
    with app.app_context():
        assert turnstile.verify_turnstile_response("token") == (
            False,
            ["invalid-input-response"],
        )
