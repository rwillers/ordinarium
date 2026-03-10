from ordinarium.service_rubric_hints import resolve_service_rubric_hints


def test_resolve_service_rubric_hints_for_supported_observances():
    assert resolve_service_rubric_hints("AdventI") == [
        "The Exhortation is traditionally read on the First Sunday of Advent."
    ]
    assert resolve_service_rubric_hints("LentI") == [
        "The Exhortation is traditionally read on the First Sunday in Lent."
    ]
    assert resolve_service_rubric_hints("TrinitySunday") == [
        "The Exhortation is traditionally read on Trinity Sunday.",
        "The Athanasian Creed may be used on Trinity Sunday.",
    ]


def test_resolve_service_rubric_hints_for_unsupported_observance():
    assert resolve_service_rubric_hints("Christmas") == []
    assert resolve_service_rubric_hints("") == []


def test_service_page_shows_rubric_hints_for_trinity_sunday(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=311,
        title="Trinity Sunday",
        service_date="2026-05-31",
        season="Trinitytide",
        observance_handle="TrinitySunday",
    )

    response = client.get(f"/service/{service_id}")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Rubric hints" in body
    assert "The Exhortation is traditionally read on Trinity Sunday." in body
    assert "The Athanasian Creed may be used on Trinity Sunday." in body


def test_service_page_hides_rubric_hints_when_no_hints_apply(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=312,
        title="Christmas Day",
        service_date="2026-12-25",
        season="Christmastide",
        observance_handle="Christmas",
    )

    response = client.get(f"/service/{service_id}")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Rubric hints" not in body
    assert "The Athanasian Creed may be used on Trinity Sunday." not in body


def test_service_page_renders_order_preset_controls_for_dated_service(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=313,
        title="First Sunday in Advent",
        service_date="2026-11-29",
        season="Advent",
        observance_handle="AdventI",
    )

    response = client.get(f"/service/{service_id}")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Reorder:" in body
    assert 'data-plan-preset-select' in body
    assert '<option value="default">Default order</option>' in body
    assert '<option value="penitential">Penitential Order</option>' in body
    assert 'data-plan-preset-select disabled' not in body


def test_service_page_disables_order_preset_controls_without_date(
    auth_client, service_factory
):
    client, user_id = auth_client
    service_id = service_factory(
        user_id=user_id,
        service_id=314,
        title="Undated service",
        service_date=None,
        season=None,
        observance_handle=None,
    )

    response = client.get(f"/service/{service_id}")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert 'data-plan-preset-select disabled' in body
