from ordinarium import pco_client


class FakeClock:
    def __init__(self):
        self.now = 0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"ok": True}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


def _install_limiter(monkeypatch, limit=100, period=20):
    clock = FakeClock()
    limiter = pco_client.PcoRateLimiter(
        default_limit=limit,
        default_period_seconds=period,
        sleep_func=clock.sleep,
        monotonic_func=clock.monotonic,
    )
    monkeypatch.setattr(pco_client, "rate_limiter", limiter)
    return clock


def test_pco_api_request_proceeds_under_rate_limit(monkeypatch):
    clock = _install_limiter(monkeypatch, limit=3, period=20)
    calls = []

    def fake_request(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeResponse()

    monkeypatch.setattr(pco_client.requests, "request", fake_request)

    pco_client.api_request("GET", "https://example.test", "/one", "token")
    pco_client.api_request("GET", "https://example.test", "/two", "token")

    assert len(calls) == 2
    assert clock.sleeps == []


def test_pco_api_request_waits_before_exceeding_fallback_window(monkeypatch):
    clock = _install_limiter(monkeypatch, limit=2, period=20)
    monkeypatch.setattr(
        pco_client.requests,
        "request",
        lambda *args, **kwargs: FakeResponse(),
    )

    pco_client.api_request("GET", "https://example.test", "/one", "token")
    pco_client.api_request("GET", "https://example.test", "/two", "token")
    pco_client.api_request("GET", "https://example.test", "/three", "token")

    assert clock.sleeps == [20]


def test_pco_api_request_updates_limiter_from_headers(monkeypatch):
    clock = _install_limiter(monkeypatch, limit=100, period=20)
    responses = [
        FakeResponse(
            headers={
                "X-PCO-API-Request-Rate-Limit": "2",
                "X-PCO-API-Request-Rate-Period": "10 seconds",
                "X-PCO-API-Request-Rate-Count": "2",
            }
        ),
        FakeResponse(),
    ]

    def fake_request(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(pco_client.requests, "request", fake_request)

    pco_client.api_request("GET", "https://example.test", "/one", "token")
    pco_client.api_request("GET", "https://example.test", "/two", "token")

    assert clock.sleeps == [10]


def test_pco_api_request_retries_after_429_retry_after(monkeypatch):
    clock = _install_limiter(monkeypatch, limit=100, period=20)
    responses = [
        FakeResponse(
            status_code=429,
            payload={"errors": [{"detail": "Rate limit exceeded."}]},
            headers={"Retry-After": "2"},
        ),
        FakeResponse(payload={"ok": True, "retried": True}),
    ]

    def fake_request(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(pco_client.requests, "request", fake_request)

    payload = pco_client.api_request("GET", "https://example.test", "/one", "token")

    assert payload == {"ok": True, "retried": True}
    assert clock.sleeps == [2]
