from ordinarium.db import get_database_gateway
from ordinarium.service_share_store import (
    get_or_create_service_share,
    get_service_id_by_share_uuid,
)
from ordinarium.service_store import (
    blank_service_payload,
    create_service_record,
    get_service_record,
)
from ordinarium.user_store import create_user, get_user_by_email


def test_representative_user_service_and_share_workflow(app):
    with app.app_context():
        gateway = get_database_gateway()
        user = create_user(
            "Grace",
            "Hopper",
            "grace@example.com",
            "test-password-hash",
            "2026-07-17T12:00:00",
        )

        assert user["id"] == 2
        assert get_user_by_email("grace@example.com")["id"] == user["id"]

        payload = blank_service_payload(user["id"])
        payload.update(
            title="D1 persistence proof",
            season="Ordinary Time",
            service_date="2026-07-19",
        )
        service_id = create_service_record(gateway, payload)
        service = get_service_record(gateway, service_id, user["id"])

        assert service_id == 3
        assert service["title"] == "D1 persistence proof"

        share = get_or_create_service_share(service_id, user["id"])
        repeated_share = get_or_create_service_share(service_id, user["id"])

        assert share["created"] is True
        assert repeated_share == {
            "share_uuid": share["share_uuid"],
            "created": False,
        }
        assert get_service_id_by_share_uuid(share["share_uuid"]) == service_id


def test_service_share_rejects_non_owner(app):
    with app.app_context():
        assert get_or_create_service_share(1, 999) is None
