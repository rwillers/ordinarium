from __future__ import annotations

from datetime import datetime

from .db import get_db


def get_pco_connection(user_id, db=None):
    if not user_id:
        return None
    db = db or get_db()
    return db.execute(
        """
        select
          user_id,
          access_token,
          refresh_token,
          token_type,
          scope,
          expires_at,
          pco_account_name,
          created_at,
          updated_at
        from pco_connections
        where user_id=?
        limit 1
        """,
        (user_id,),
    ).fetchone()


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
    db = db or get_db()
    db.execute(
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
          updated_at=CURRENT_TIMESTAMP
        """,
        (
            user_id,
            access_token,
            refresh_token,
            token_type,
            scope,
            expires_at,
            pco_account_name,
        ),
    )


def delete_pco_connection(user_id, db=None):
    if not user_id:
        return
    db = db or get_db()
    db.execute("delete from pco_connections where user_id=?", (user_id,))


def clear_upcoming_service_pco_links_for_user(user_id, on_or_after_date, db=None):
    if not user_id or not on_or_after_date:
        return
    db = db or get_db()
    db.execute(
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
    )


def get_service_pco_link(service_id, db=None):
    if not service_id:
        return None
    db = db or get_db()
    return db.execute(
        """
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
        """,
        (service_id,),
    ).fetchone()


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
    db = db or get_db()
    db.execute(
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
    db = db or get_db()
    db.execute("delete from service_pco_links where service_id=?", (service_id,))


def update_service_pco_sync_status(
    service_id,
    status,
    error=None,
    synced_at=None,
    db=None,
):
    if not service_id:
        return
    db = db or get_db()
    synced_at = synced_at or datetime.utcnow().isoformat()
    db.execute(
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
