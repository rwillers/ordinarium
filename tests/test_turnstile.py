import json

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
