from .db import get_database_gateway


def load_custom_elements(service_id, user_id=None):
    if not service_id:
        return []
    db = get_database_gateway()
    if user_id:
        rows = db.fetch_all(
            "select id, title, text, created_at from service_custom_elements where service_id=? and user_id=? order by created_at, id",
            (service_id, user_id),
        )
    else:
        rows = db.fetch_all(
            "select id, title, text, created_at from service_custom_elements where service_id=? order by created_at, id",
            (service_id,),
        )
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "text": row["text"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def load_custom_templates(user_id):
    if not user_id:
        return []
    db = get_database_gateway()
    rows = db.fetch_all(
        "select id, title, text, created_at, updated_at from service_custom_templates where user_id=? order by updated_at desc, id desc",
        (user_id,),
    )
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "text": row["text"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
