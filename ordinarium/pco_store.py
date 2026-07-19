from __future__ import annotations

import time
import uuid
from datetime import datetime

from .db import get_database_gateway
from .infrastructure import DatabaseStatement
from .token_encryption import decrypt_token, encrypt_token


def get_pco_connection(user_id, db=None):
    if not user_id:
        return None
    db = _database(db)
    sql = """
        select
          user_id,
          access_token,
          refresh_token,
          token_type,
          scope,
          expires_at,
          pco_account_name,
          version,
          refresh_claim_token,
          refresh_claim_expires_at,
          created_at,
          updated_at
        from pco_connections
        where user_id=?
        limit 1
        """
    row = _fetch_one(db, sql, (user_id,))
    if not row:
        return None
    connection = dict(row)
    connection["access_token"] = decrypt_token(
        connection.get("access_token"),
        user_id=user_id,
        field_name="access_token",
    )
    connection["refresh_token"] = decrypt_token(
        connection.get("refresh_token"),
        user_id=user_id,
        field_name="refresh_token",
    )
    return connection


def claim_pco_connection_refresh(connection, lease_seconds=60, db=None):
    """Claim a token version so concurrent refreshes cannot overwrite each other."""
    if not connection:
        return None
    claim_token = uuid.uuid4().hex
    now = int(time.time())
    cursor = _execute(
        _database(db),
        """
        update pco_connections set
          refresh_claim_token=?, refresh_claim_expires_at=?, updated_at=CURRENT_TIMESTAMP
        where user_id=? and version=?
          and (refresh_claim_token is null or coalesce(refresh_claim_expires_at, 0) <= ?)
        """,
        (
            claim_token,
            now + int(lease_seconds),
            connection["user_id"],
            int(connection.get("version") or 1),
            now,
        ),
    )
    return claim_token if _changes(cursor) == 1 else None


def complete_pco_connection_refresh(connection, claim_token, token, db=None):
    """Persist refreshed encrypted tokens only if the claimed version is current."""
    encrypted_access_token = encrypt_token(
        token.access_token,
        user_id=connection["user_id"],
        field_name="access_token",
    )
    encrypted_refresh_token = encrypt_token(
        token.refresh_token,
        user_id=connection["user_id"],
        field_name="refresh_token",
    )
    cursor = _execute(
        _database(db),
        """
        update pco_connections set
          access_token=?, refresh_token=coalesce(?, refresh_token), token_type=?,
          scope=?, expires_at=?, version=version + 1,
          refresh_claim_token=null, refresh_claim_expires_at=null,
          updated_at=CURRENT_TIMESTAMP
        where user_id=? and version=? and refresh_claim_token=?
        """,
        (
            encrypted_access_token,
            encrypted_refresh_token,
            token.token_type,
            token.scope,
            token.expires_at,
            connection["user_id"],
            int(connection.get("version") or 1),
            claim_token,
        ),
    )
    return _changes(cursor) == 1


def release_pco_connection_refresh(connection, claim_token, db=None):
    cursor = _execute(
        _database(db),
        """
        update pco_connections set
          refresh_claim_token=null, refresh_claim_expires_at=null,
          updated_at=CURRENT_TIMESTAMP
        where user_id=? and version=? and refresh_claim_token=?
        """,
        (
            connection["user_id"],
            int(connection.get("version") or 1),
            claim_token,
        ),
    )
    return _changes(cursor) == 1


def pco_connection_exists(user_id, db=None):
    """Return whether a user has a connection without reading token material."""
    if not user_id:
        return False
    db = _database(db)
    row = _fetch_one(
        db,
        "select user_id from pco_connections where user_id=? limit 1",
        (user_id,),
    )
    return row is not None


def upsert_pco_connection(
    user_id,
    access_token,
    refresh_token=None,
    token_type=None,
    scope=None,
    expires_at=None,
    pco_account_name=None,
    db=None,
):
    if not user_id:
        return
    db = _database(db)
    encrypted_access_token = encrypt_token(
        access_token,
        user_id=user_id,
        field_name="access_token",
    )
    encrypted_refresh_token = encrypt_token(
        refresh_token,
        user_id=user_id,
        field_name="refresh_token",
    )
    _execute(
        db,
        """
        insert into pco_connections (
          user_id,
          access_token,
          refresh_token,
          token_type,
          scope,
          expires_at,
          pco_account_name,
          created_at,
          updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        on conflict(user_id) do update set
          access_token=excluded.access_token,
          refresh_token=excluded.refresh_token,
          token_type=excluded.token_type,
          scope=excluded.scope,
          expires_at=excluded.expires_at,
          pco_account_name=coalesce(
            excluded.pco_account_name,
            pco_connections.pco_account_name
          ),
          version=pco_connections.version + 1,
          refresh_claim_token=null,
          refresh_claim_expires_at=null,
          updated_at=CURRENT_TIMESTAMP
        """,
        (
            user_id,
            encrypted_access_token,
            encrypted_refresh_token,
            token_type,
            scope,
            expires_at,
            pco_account_name,
        ),
    )


def delete_pco_connection(user_id, db=None):
    if not user_id:
        return
    db = _database(db)
    _execute(db, "delete from pco_connections where user_id=?", (user_id,))


def clear_upcoming_service_pco_links_for_user(user_id, on_or_after_date, db=None):
    if not user_id or not on_or_after_date:
        return
    db = _database(db)
    statements = [
        DatabaseStatement(
            """
            delete from service_pco_item_links
            where service_id in (
              select id
              from services
              where user_id=?
                and service_date is not null
                and service_date >= ?
            )
            """,
            (user_id, on_or_after_date),
        ),
        DatabaseStatement(
            """
            delete from service_pco_links
            where service_id in (
              select id
              from services
              where user_id=?
                and service_date is not null
                and service_date >= ?
            )
            """,
            (user_id, on_or_after_date),
        ),
    ]
    _batch(db, statements)


def get_service_pco_link(service_id, db=None):
    if not service_id:
        return None
    db = _database(db)
    sql = """
        select
          id,
          service_id,
          pco_service_type_id,
          pco_service_type_name,
          pco_plan_id,
          pco_plan_title,
          last_synced_at,
          last_sync_status,
          last_sync_error,
          created_at,
          updated_at
        from service_pco_links
        where service_id=?
        limit 1
        """
    return _fetch_one(db, sql, (service_id,))


def upsert_service_pco_link(
    service_id,
    pco_service_type_id,
    pco_plan_id,
    pco_service_type_name=None,
    pco_plan_title=None,
    db=None,
):
    if not service_id:
        return
    db = _database(db)
    existing = get_service_pco_link(service_id, db=db)
    if existing and (
        existing["pco_service_type_id"] != pco_service_type_id
        or existing["pco_plan_id"] != pco_plan_id
    ):
        clear_service_pco_item_links(service_id, db=db)
    _execute(
        db,
        """
        insert into service_pco_links (
          service_id,
          pco_service_type_id,
          pco_service_type_name,
          pco_plan_id,
          pco_plan_title,
          created_at,
          updated_at
        ) values (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        on conflict(service_id) do update set
          pco_service_type_id=excluded.pco_service_type_id,
          pco_service_type_name=excluded.pco_service_type_name,
          pco_plan_id=excluded.pco_plan_id,
          pco_plan_title=excluded.pco_plan_title,
          updated_at=CURRENT_TIMESTAMP
        """,
        (
            service_id,
            pco_service_type_id,
            pco_service_type_name,
            pco_plan_id,
            pco_plan_title,
        ),
    )


def clear_service_pco_link(service_id, db=None):
    if not service_id:
        return
    db = _database(db)
    clear_service_pco_item_links(service_id, db=db)
    _execute(db, "delete from service_pco_links where service_id=?", (service_id,))


def list_service_pco_item_links(service_id, db=None):
    if not service_id:
        return []
    db = _database(db)
    rows = _fetch_all(
        db,
        """
        select
          id,
          service_id,
          ordinarium_token,
          pco_item_id,
          last_content_hash,
          last_position,
          created_at,
          updated_at
        from service_pco_item_links
        where service_id=?
        order by last_position, id
        """,
        (service_id,),
    )
    return [dict(row) for row in rows]


def upsert_service_pco_item_link(
    service_id,
    ordinarium_token,
    pco_item_id,
    last_content_hash=None,
    last_position=None,
    db=None,
):
    if not service_id or not ordinarium_token or not pco_item_id:
        return
    db = _database(db)
    _execute(
        db,
        """
        insert into service_pco_item_links (
          service_id,
          ordinarium_token,
          pco_item_id,
          last_content_hash,
          last_position,
          created_at,
          updated_at
        ) values (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        on conflict(service_id, ordinarium_token) do update set
          pco_item_id=excluded.pco_item_id,
          last_content_hash=excluded.last_content_hash,
          last_position=excluded.last_position,
          updated_at=CURRENT_TIMESTAMP
        """,
        (
            service_id,
            ordinarium_token,
            pco_item_id,
            last_content_hash,
            last_position,
        ),
    )


def delete_service_pco_item_link(service_id, ordinarium_token, db=None):
    if not service_id or not ordinarium_token:
        return
    db = _database(db)
    _execute(
        db,
        """
        delete from service_pco_item_links
        where service_id=? and ordinarium_token=?
        """,
        (service_id, ordinarium_token),
    )


def clear_service_pco_item_links(service_id, db=None):
    if not service_id:
        return
    db = _database(db)
    _execute(
        db,
        "delete from service_pco_item_links where service_id=?",
        (service_id,),
    )


def update_service_pco_sync_status(
    service_id,
    status,
    error=None,
    synced_at=None,
    db=None,
):
    if not service_id:
        return
    db = _database(db)
    synced_at = synced_at or datetime.utcnow().isoformat()
    _execute(
        db,
        """
        update service_pco_links set
          last_synced_at=?,
          last_sync_status=?,
          last_sync_error=?,
          updated_at=CURRENT_TIMESTAMP
        where service_id=?
        """,
        (synced_at, status, error, service_id),
    )


def _database(db):
    return db or get_database_gateway()


def _fetch_one(db, sql, params=()):
    if hasattr(db, "fetch_one"):
        return db.fetch_one(sql, params)
    return db.execute(sql, params).fetchone()


def _fetch_all(db, sql, params=()):
    if hasattr(db, "fetch_all"):
        return db.fetch_all(sql, params)
    return db.execute(sql, params).fetchall()


def _execute(db, sql, params=()):
    return db.execute(sql, params)


def _batch(db, statements):
    if hasattr(db, "batch"):
        return db.batch(statements)
    for statement in statements:
        db.execute(statement.sql, statement.params)
    return []


def _changes(cursor):
    if hasattr(cursor, "changes"):
        return cursor.changes
    return cursor.rowcount
