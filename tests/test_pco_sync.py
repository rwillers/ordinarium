from ordinarium import pco_sync


def test_list_plan_templates_paginates(monkeypatch):
    calls = []

    def fake_api_request(
        method,
        base_url,
        path,
        access_token,
        json=None,
        params=None,
        absolute_url=False,
    ):
        calls.append((method, base_url, path, access_token, absolute_url))
        if not absolute_url:
            return {
                "data": [{"id": "template-1"}],
                "links": {"next": "https://example.test/next"},
            }
        return {"data": [{"id": "template-2"}], "links": {}}

    monkeypatch.setattr(pco_sync, "api_request", fake_api_request)

    templates = pco_sync.list_plan_templates(
        "https://example.test", "token", "service-type-1"
    )

    assert templates == [{"id": "template-1"}, {"id": "template-2"}]
    assert calls == [
        (
            "GET",
            "https://example.test",
            "/services/v2/service_types/service-type-1/plan_templates",
            "token",
            False,
        ),
        (
            "GET",
            "https://example.test",
            "https://example.test/next",
            "token",
            True,
        ),
    ]


def test_import_plan_template_calls_import_action(monkeypatch):
    calls = []

    def fake_api_request(method, base_url, path, access_token, json=None):
        calls.append((method, base_url, path, access_token, json))
        return {"data": {"id": "imported"}}

    monkeypatch.setattr(pco_sync, "api_request", fake_api_request)

    result = pco_sync.import_plan_template(
        "https://example.test",
        "token",
        "service-type-1",
        "plan-1",
        "template-1",
    )

    assert result == {"data": {"id": "imported"}}
    assert calls == [
        (
            "POST",
            "https://example.test",
            "/services/v2/service_types/service-type-1/plans/plan-1/import_template",
            "token",
            {"data": {"type": "PlanTemplate", "id": "template-1"}},
        )
    ]
