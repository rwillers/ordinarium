from .db import get_database_gateway


def list_active_users():
    return get_database_gateway().fetch_all(
        """
        select id, first_name, last_name, email, feature_flags,
               created_at, last_accessed_at
        from users
        where deleted_at is null
        order by id asc
        """
    )


def count_user_services(user_id):
    row = get_database_gateway().fetch_one(
        "select count(*) as total from services where user_id=?",
        (user_id,),
    )
    return row["total"] if row else 0


def update_user_administration(user_id, first_name, last_name, email, feature_flags):
    get_database_gateway().execute(
        """
        update users
        set first_name=?, last_name=?, email=?, feature_flags=?
        where id=?
        """,
        (first_name, last_name, email, feature_flags, user_id),
    )


def soft_delete_user(user_id, deleted_at):
    get_database_gateway().execute(
        "update users set deleted_at=? where id=?",
        (deleted_at, user_id),
    )


def soft_delete_users(user_ids, deleted_at):
    if not user_ids:
        return
    placeholders = ",".join(["?"] * len(user_ids))
    get_database_gateway().execute(
        f"update users set deleted_at=? where id in ({placeholders})",
        (deleted_at, *user_ids),
    )
