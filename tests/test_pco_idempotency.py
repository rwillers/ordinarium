from datetime import date, timedelta

import pytest

from ordinarium.db import get_gateway_connection
from ordinarium import pco_plan_operations, pco_sync


def test_plan_operation_lease_outlives_worker_and_provider_deadlines():
    assert pco_plan_operations.PLAN_OPERATION_LEASE_SECONDS >= 180


def test_plan_operation_reconciles_provider_success_before_d1_write(
    app, user_factory, service_factory, monkeypatch
):
    user_id = user_factory(email="plan-reconcile@example.com")
    service_id = service_factory(
        user_id=user_id,
        service_id=911,
        service_date=(date.today() + timedelta(days=3)).isoformat(),
    )
    remote_plans = []
    creates = []
    monkeypatch.setattr(
        pco_plan_operations,
        "list_plans_by_title",
        lambda *_args: list(remote_plans),
    )
    monkeypatch.setattr(pco_plan_operations, "list_plan_times", lambda *_args: [])
    monkeypatch.setattr(
        pco_plan_operations, "create_plan_time", lambda *_args: {"data": {"id": "t1"}}
    )
    monkeypatch.setattr(
        pco_plan_operations, "import_plan_template", lambda *_args: None
    )

    def create(*_args):
        creates.append("create")
        remote = {"id": "remote-plan-1", "attributes": {"title": "Sunday"}}
        remote_plans.append(remote)
        return {"data": remote}

    monkeypatch.setattr(pco_plan_operations, "create_plan", create)
    original_advance = pco_plan_operations._advance_operation
    interrupted = False

    def advance(*args, **kwargs):
        nonlocal interrupted
        if args[3] == "plan_created" and not interrupted:
            interrupted = True
            raise RuntimeError("simulated D1 interruption")
        return original_advance(*args, **kwargs)

    monkeypatch.setattr(pco_plan_operations, "_advance_operation", advance)
    values = {
        "service_type_id": "type-1",
        "service_type_name": "Sunday",
        "plan_title": "Sunday",
        "plan_date": (date.today() + timedelta(days=3)).isoformat(),
        "plan_time": "10:00",
        "timezone_offset": "0",
        "template_id": None,
        "series_title": None,
    }
    with app.app_context():
        db = get_gateway_connection()
        with pytest.raises(RuntimeError, match="simulated D1 interruption"):
            pco_plan_operations.complete_pco_plan_operation(
                db=db,
                user_id=user_id,
                service_id=service_id,
                access_token="token",
                base_url="base",
                values=values,
            )
        plan_id, _title, _operation_id = (
            pco_plan_operations.complete_pco_plan_operation(
                db=db,
                user_id=user_id,
                service_id=service_id,
                access_token="token",
                base_url="base",
                values=values,
            )
        )

    assert plan_id == "remote-plan-1"
    assert creates == ["create"]


def test_item_marker_reconciles_provider_success_before_link_write(
    app, user_factory, service_factory, monkeypatch
):
    user_id = user_factory(email="item-reconcile@example.com")
    service_id = service_factory(user_id=user_id, service_id=912)
    remote_items = []
    creates = []
    payloads = [
        {
            "token": "text:collect",
            "position": 0,
            "content_hash": "hash-1",
            "payload": {
                "data": {
                    "type": "Item",
                    "attributes": {"title": "Collect", "html_details": "<p>Text</p>"},
                }
            },
        }
    ]
    monkeypatch.setattr(pco_sync, "list_plan_items", lambda *_args: list(remote_items))

    def create(*args):
        creates.append("create")
        remote_items.append(
            {"id": "item-1", "attributes": args[4]["data"]["attributes"]}
        )
        return {"data": {"id": "item-1"}}

    monkeypatch.setattr(pco_sync, "create_plan_item", create)
    original_upsert = pco_sync.upsert_service_pco_item_link
    interrupted = False

    def upsert(*args, **kwargs):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise RuntimeError("simulated D1 interruption")
        return original_upsert(*args, **kwargs)

    monkeypatch.setattr(pco_sync, "upsert_service_pco_item_link", upsert)
    with app.app_context():
        with pytest.raises(RuntimeError, match="simulated D1 interruption"):
            pco_sync._sync_pco_item_delta(
                service_id, "base", "token", "type-1", "plan-1", payloads
            )
        pco_sync._sync_pco_item_delta(
            service_id, "base", "token", "type-1", "plan-1", payloads
        )
        links = pco_sync.list_service_pco_item_links(service_id)

    assert creates == ["create"]
    assert links[0]["pco_item_id"] == "item-1"
