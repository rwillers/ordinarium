import uuid

from .db import get_database_gateway


def get_or_create_service_share(service_id, user_id):
    gateway = get_database_gateway()
    owner = gateway.fetch_one(
        "select user_id from services where id=? limit 1",
        (service_id,),
    )
    if not owner or owner["user_id"] != user_id:
        return None

    existing = gateway.fetch_one(
        "select share_uuid from service_shares where service_id=? limit 1",
        (service_id,),
    )
    if existing:
        return {"share_uuid": existing["share_uuid"], "created": False}

    share_id = gateway.allocate_id("service_shares")
    share_uuid = str(uuid.uuid4())
    gateway.execute(
        """
        insert into service_shares (id, service_id, share_uuid)
        values (?, ?, ?)
        """,
        (share_id, service_id, share_uuid),
    )
    return {"share_uuid": share_uuid, "created": True}


def get_service_id_by_share_uuid(share_uuid):
    if not share_uuid:
        return None
    row = get_database_gateway().fetch_one(
        "select service_id from service_shares where share_uuid=? limit 1",
        (share_uuid,),
    )
    return row["service_id"] if row else None
