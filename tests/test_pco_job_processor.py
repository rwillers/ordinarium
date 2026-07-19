from datetime import date, timedelta

import pytest
import requests

from ordinarium.db import get_gateway_connection
from ordinarium.pco_batch_jobs import (
    claim_pco_batch_sync_row,
    create_pco_batch_sync_job,
    get_pco_batch_sync_job,
    list_pco_batch_sync_rows,
)
from ordinarium.pco_job_errors import RetryablePcoJobError
from ordinarium.pco_job_errors import raise_if_retryable_pco_error
from ordinarium.pco_client import PcoApiError
from ordinarium.pco_sync import PcoSyncError
from ordinarium import pco_job_processor, service_pco_routes


def _payload(service_id, mode="sync_linked"):
    return {
        "rows": [{"service_id": service_id, "mode": mode}],
        "pco_plan_time": "10:00",
        "pco_plan_tz_offset": "0",
    }


def _message(job_id, row_id, user_id):
    return {"job_id": job_id, "row_id": row_id, "user_id": user_id}


def _setup_job(app, user_factory, service_factory, mode="sync_linked"):
    user_id = user_factory(email=f"pco-job-{mode}@example.com")
    service_id = service_factory(
        user_id=user_id,
        service_id=901,
        service_date=(date.today() + timedelta(days=2)).isoformat(),
    )
    with app.app_context():
        db = get_gateway_connection()
        job_id = create_pco_batch_sync_job(user_id, _payload(service_id, mode), db=db)
        row = list_pco_batch_sync_rows(job_id, db=db)[0]
    return user_id, service_id, job_id, row


def test_duplicate_delivery_runs_provider_once(
    app, user_factory, service_factory, monkeypatch
):
    user_id, service_id, job_id, row = _setup_job(app, user_factory, service_factory)
    calls = []
    monkeypatch.setattr(
        pco_job_processor,
        "get_valid_pco_connection",
        lambda *_args: {"access_token": "token"},
    )
    monkeypatch.setattr(
        pco_job_processor,
        "_load_batch_links",
        lambda *_args: {
            service_id: {
                "service_id": service_id,
                "pco_service_type_id": "type-1",
                "pco_plan_id": "plan-1",
            }
        },
    )

    def execute(prepared, *_args, **_kwargs):
        calls.append(prepared["service_id"])
        return {
            "service_id": service_id,
            "mode": "sync_linked",
            "status": "success",
            "error": "",
            "pco_service_type_id": "type-1",
            "pco_plan_id": "plan-1",
        }

    monkeypatch.setattr(pco_job_processor, "_execute_pco_batch_row", execute)
    with app.app_context():
        db = get_gateway_connection()
        first = pco_job_processor.process_pco_row_message(
            _message(job_id, row["id"], user_id), db=db
        )
        second = pco_job_processor.process_pco_row_message(
            _message(job_id, row["id"], user_id), db=db
        )

    assert first[0]["disposition"] == "terminal"
    assert second[0]["reason"] == "duplicate"
    assert calls == [service_id]


def test_transient_failure_releases_row_then_retry_succeeds(
    app, user_factory, service_factory, monkeypatch
):
    user_id, service_id, job_id, row = _setup_job(app, user_factory, service_factory)
    monkeypatch.setattr(
        pco_job_processor,
        "get_valid_pco_connection",
        lambda *_args: {"access_token": "token"},
    )
    monkeypatch.setattr(pco_job_processor, "_load_batch_links", lambda *_args: {})
    attempts = 0

    def execute(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryablePcoJobError(
                "rate limited", category="rate_limit", retry_after_seconds=41
            )
        return {
            "service_id": service_id,
            "mode": "sync_linked",
            "status": "failed",
            "error": "Planning Center plan not linked.",
        }

    monkeypatch.setattr(pco_job_processor, "_execute_pco_batch_row", execute)
    with app.app_context():
        db = get_gateway_connection()
        first = pco_job_processor.process_pco_row_message(
            _message(job_id, row["id"], user_id), db=db
        )
        released = list_pco_batch_sync_rows(job_id, db=db)[0]
        second = pco_job_processor.process_pco_row_message(
            _message(job_id, row["id"], user_id), db=db
        )

    assert first[1] == 429
    assert first[0]["retry_after_seconds"] == 41
    assert released["status"] == "retry"
    assert second[0]["disposition"] == "terminal"
    assert attempts == 2


def test_missing_connection_is_terminal_and_dlq_aggregates(
    app, user_factory, service_factory, monkeypatch
):
    user_id, _service_id, job_id, row = _setup_job(app, user_factory, service_factory)
    monkeypatch.setattr(
        pco_job_processor, "get_valid_pco_connection", lambda *_args: None
    )
    with app.app_context():
        db = get_gateway_connection()
        response = pco_job_processor.process_pco_row_message(
            _message(job_id, row["id"], user_id), db=db
        )
        job = get_pco_batch_sync_job(job_id, user_id, db=db)

    assert response[0]["disposition"] == "terminal"
    assert job["status"] == "succeeded"
    assert job["summary"]["failed"] == 1
    assert job["results"][0]["error"] == "Planning Center is not connected."


def test_dlq_terminalizes_retry_exhausted_row(app, user_factory, service_factory):
    user_id, _service_id, job_id, row = _setup_job(app, user_factory, service_factory)
    with app.app_context():
        db = get_gateway_connection()
        response = pco_job_processor.dead_letter_pco_row_message(
            _message(job_id, row["id"], user_id), db=db
        )
        job = get_pco_batch_sync_job(job_id, user_id, db=db)

    assert response[0]["reason"] == "retry_exhausted"
    assert job["status"] == "succeeded"
    assert job["results"][0]["status"] == "failed"


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (requests.ConnectionError("network"), "network"),
        (PcoApiError("limited", status_code=429), "rate_limit"),
        (PcoApiError("unavailable", status_code=503), "provider"),
    ],
)
def test_network_rate_limit_and_provider_errors_remain_retryable(error, category):
    with pytest.raises(RetryablePcoJobError) as raised:
        raise_if_retryable_pco_error(error)

    assert raised.value.category == category


def test_create_new_uses_durable_operation_and_persists_remote_ids(
    app, user_factory, service_factory, monkeypatch
):
    user_id = user_factory(email="pco-job-create-new@example.com")
    service_id = service_factory(
        user_id=user_id,
        service_id=902,
        service_date=(date.today() + timedelta(days=3)).isoformat(),
        title="Sunday",
    )
    payload = _payload(service_id, "create_new")
    payload["rows"][0]["pco_service_type_id"] = "type-1"
    monkeypatch.setattr(
        pco_job_processor,
        "get_valid_pco_connection",
        lambda *_args: {"access_token": "token"},
    )
    calls = []

    def complete_operation(**kwargs):
        calls.append(kwargs["values"])
        kwargs["db"].execute(
            """
            insert into pco_plan_operations (
              id, operation_key, user_id, service_id, mode, pco_service_type_id,
              pco_plan_id, pco_plan_title, status, step
            ) values (?, ?, ?, ?, 'create_new', ?, ?, ?, 'completed', 'completed')
            """,
            (
                "operation-1",
                "operation-key-1",
                user_id,
                service_id,
                "type-1",
                "plan-1",
                "Sunday",
            ),
        )
        return "plan-1", "Sunday", "operation-1"

    monkeypatch.setattr(
        service_pco_routes, "complete_pco_plan_operation", complete_operation
    )
    monkeypatch.setattr(
        service_pco_routes,
        "_run_service_sync",
        lambda *_args, **_kwargs: (
            True,
            {"synced_at": "2099-01-01T00:00:00", "item_count": 1},
        ),
    )
    with app.app_context():
        db = get_gateway_connection()
        job_id = create_pco_batch_sync_job(user_id, payload, db=db)
        row = list_pco_batch_sync_rows(job_id, db=db)[0]
        response = pco_job_processor.process_pco_row_message(
            _message(job_id, row["id"], user_id), db=db
        )
        completed = list_pco_batch_sync_rows(job_id, db=db)[0]

    assert response[0]["disposition"] == "terminal"
    assert len(calls) == 1
    assert completed["plan_operation_id"] == "operation-1"
    assert completed["effective_plan_id"] == "plan-1"


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (PcoApiError("bad request", status_code=400), "validation"),
        (PcoApiError("not found", status_code=404), "validation"),
        (
            PcoSyncError(
                "Planning Center template import has an uncertain result and requires manual resolution."
            ),
            "manual_resolution",
        ),
    ],
)
def test_deterministic_provider_errors_are_persisted_terminal(
    app, user_factory, service_factory, monkeypatch, error, category
):
    user_id, _service_id, job_id, row = _setup_job(app, user_factory, service_factory)
    monkeypatch.setattr(
        pco_job_processor,
        "get_valid_pco_connection",
        lambda *_args: {"access_token": "token"},
    )
    monkeypatch.setattr(pco_job_processor, "_load_batch_links", lambda *_args: {})
    monkeypatch.setattr(
        pco_job_processor,
        "_execute_pco_batch_row",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )
    with app.app_context():
        db = get_gateway_connection()
        response = pco_job_processor.process_pco_row_message(
            _message(job_id, row["id"], user_id), db=db
        )
        completed = list_pco_batch_sync_rows(job_id, db=db)[0]

    assert response[0]["disposition"] == "terminal"
    assert completed["status"] == "failed"
    assert completed["error_category"] == category
    assert str(error) in completed["result"]["error"]


def test_claims_use_fresh_epochs_and_safe_lease_window(
    app, user_factory, service_factory, monkeypatch
):
    user_id, service_id, job_id, row = _setup_job(app, user_factory, service_factory)
    monkeypatch.setattr(
        pco_job_processor,
        "get_valid_pco_connection",
        lambda *_args: {"access_token": "token"},
    )
    monkeypatch.setattr(pco_job_processor, "_load_batch_links", lambda *_args: {})
    monkeypatch.setattr(
        pco_job_processor,
        "_execute_pco_batch_row",
        lambda *_args, **_kwargs: {
            "service_id": service_id,
            "mode": "sync_linked",
            "status": "failed",
            "error": "not linked",
        },
    )
    epochs = iter([1_000, 1_075])
    monkeypatch.setattr(pco_job_processor.time, "time", lambda: next(epochs))
    row_claims = []
    service_claims = []
    original_row_claim = pco_job_processor.claim_pco_batch_sync_row
    original_service_claim = pco_job_processor.claim_pco_service_sync

    def row_claim(*args, **kwargs):
        row_claims.append((args[4], kwargs["now_epoch"]))
        return original_row_claim(*args, **kwargs)

    def service_claim(*args, **kwargs):
        service_claims.append((args[2], kwargs["now_epoch"]))
        return original_service_claim(*args, **kwargs)

    monkeypatch.setattr(pco_job_processor, "claim_pco_batch_sync_row", row_claim)
    monkeypatch.setattr(pco_job_processor, "claim_pco_service_sync", service_claim)
    with app.app_context():
        db = get_gateway_connection()
        pco_job_processor.process_pco_row_message(
            _message(job_id, row["id"], user_id), db=db
        )

    assert pco_job_processor.PROVIDER_DEADLINE_SECONDS <= 90
    assert pco_job_processor.ROW_LEASE_SECONDS >= 180
    assert pco_job_processor.SERVICE_LEASE_SECONDS >= 180
    assert row_claims == [(1_180, 1_000)]
    assert service_claims == [(1_255, 1_075)]


def test_row_takeover_waits_for_full_safe_lease_window(
    app, user_factory, service_factory
):
    user_id, _service_id, job_id, row = _setup_job(app, user_factory, service_factory)
    expires_at = 1_000 + pco_job_processor.ROW_LEASE_SECONDS
    with app.app_context():
        db = get_gateway_connection()
        assert claim_pco_batch_sync_row(
            job_id,
            row["id"],
            user_id,
            "first",
            expires_at,
            now_epoch=1_000,
            db=db,
        )
        assert not claim_pco_batch_sync_row(
            job_id,
            row["id"],
            user_id,
            "too-early",
            expires_at + pco_job_processor.ROW_LEASE_SECONDS,
            now_epoch=expires_at - 1,
            db=db,
        )
        assert claim_pco_batch_sync_row(
            job_id,
            row["id"],
            user_id,
            "takeover",
            expires_at + pco_job_processor.ROW_LEASE_SECONDS,
            now_epoch=expires_at,
            db=db,
        )


def test_queued_duplicate_existing_targets_fail_before_provider_sync(
    app, user_factory, service_factory, monkeypatch
):
    user_id = user_factory(email="pco-job-duplicate-target@example.com")
    service_ids = [
        service_factory(
            user_id=user_id,
            service_id=903,
            service_date=(date.today() + timedelta(days=3)).isoformat(),
        ),
        service_factory(
            user_id=user_id,
            service_id=904,
            service_date=(date.today() + timedelta(days=4)).isoformat(),
        ),
    ]
    payload = {
        "rows": [
            {
                "service_id": service_id,
                "mode": "link_existing",
                "pco_service_type_id": "type-1",
                "pco_plan_id": "plan-1",
            }
            for service_id in service_ids
        ],
        "pco_plan_time": "10:00",
        "pco_plan_tz_offset": "0",
    }
    monkeypatch.setattr(
        pco_job_processor,
        "get_valid_pco_connection",
        lambda *_args: {"access_token": "token"},
    )
    provider_calls = []
    monkeypatch.setattr(
        service_pco_routes,
        "fetch_plan",
        lambda *_args, **_kwargs: provider_calls.append("fetch"),
    )
    monkeypatch.setattr(
        service_pco_routes,
        "_run_service_sync",
        lambda *_args, **_kwargs: provider_calls.append("sync"),
    )
    with app.app_context():
        db = get_gateway_connection()
        job_id = create_pco_batch_sync_job(user_id, payload, db=db)
        rows = list_pco_batch_sync_rows(job_id, db=db)
        responses = [
            pco_job_processor.process_pco_row_message(
                _message(job_id, row["id"], user_id), db=db
            )
            for row in rows
        ]
        completed = list_pco_batch_sync_rows(job_id, db=db)

    assert [response[0]["disposition"] for response in responses] == [
        "terminal",
        "terminal",
    ]
    assert provider_calls == []
    assert [row["status"] for row in completed] == ["failed", "failed"]
    assert all(
        "same Planning Center plan" in row["result"]["error"] for row in completed
    )
