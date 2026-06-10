from .pco_store import clear_service_pco_item_links
from .plan_tokens import parse_json_object, parse_plan_tokens
from .service_defaults import DEFAULT_RITE
from .service_store import blank_service_payload, create_service, update_service_columns


def load_service_copy_source(db, source_id, user_id):
    if not source_id:
        return None
    source = db.execute(
        """
        select
          id,
          rite,
          text_order,
          text_disabled,
          lesson_overrides,
          offertory_sentence_id,
          proper_overrides,
          service_option_values
        from services
        where id=? and user_id=? limit 1
        """,
        (source_id, user_id),
    ).fetchone()
    if not source:
        return None
    custom_rows = db.execute(
        """
        select id, title, text, created_at
        from service_custom_elements
        where service_id=? and user_id=?
        order by created_at, id
        """,
        (source_id, user_id),
    ).fetchall()
    return {
        "service": dict(source),
        "custom_rows": custom_rows,
        "order_tokens": parse_plan_tokens(source["text_order"]),
        "disabled_tokens": parse_plan_tokens(source["text_disabled"]),
        "lesson_overrides": parse_json_object(source["lesson_overrides"]),
        "offertory_sentence_id": source["offertory_sentence_id"],
        "proper_overrides": parse_json_object(source["proper_overrides"]),
        "service_option_values": parse_json_object(source["service_option_values"]),
    }


def service_copy_rite(source_copy):
    return source_copy["service"].get("rite") or DEFAULT_RITE


def create_service_from_copy(db, user_id, source_copy, base_payload):
    payload = blank_service_payload(user_id, service_copy_rite(source_copy))
    payload.update(base_payload)
    new_service_id = create_service(db, payload)
    _apply_source_copy(db, user_id, source_copy, new_service_id, payload)
    return new_service_id


def overwrite_service_from_copy(db, user_id, source_copy, target_id, target_payload):
    db.execute(
        """
        delete from service_custom_elements
        where service_id=? and user_id=?
        """,
        (target_id, user_id),
    )
    clear_service_pco_item_links(target_id, db=db)
    _apply_source_copy(db, user_id, source_copy, target_id, target_payload)


def _apply_source_copy(db, user_id, source_copy, target_id, payload):
    custom_id_map = _copy_custom_elements(
        db, user_id, source_copy["custom_rows"], target_id
    )
    payload["text_order"] = _remap_tokens(source_copy["order_tokens"], custom_id_map)
    payload["text_disabled"] = _remap_tokens(
        source_copy["disabled_tokens"], custom_id_map
    )
    payload["lesson_overrides"] = source_copy["lesson_overrides"]
    payload["offertory_sentence_id"] = source_copy["offertory_sentence_id"]
    payload["proper_overrides"] = source_copy["proper_overrides"]
    payload["service_option_values"] = source_copy["service_option_values"]
    update_service_columns(db, target_id, payload)


def _copy_custom_elements(db, user_id, custom_rows, target_id):
    custom_id_map = {}
    for row in custom_rows:
        cursor = db.execute(
            """
            insert into service_custom_elements (service_id, user_id, title, text)
            values (?, ?, ?, ?)
            """,
            (target_id, user_id, row["title"], row["text"]),
        )
        custom_id_map[row["id"]] = cursor.lastrowid
    return custom_id_map


def _remap_tokens(tokens, custom_id_map):
    remapped = []
    for token in tokens:
        if token.startswith("custom:"):
            try:
                old_id = int(token.split(":", 1)[1])
            except (IndexError, ValueError):
                continue
            new_id = custom_id_map.get(old_id)
            if new_id:
                remapped.append(f"custom:{new_id}")
            continue
        remapped.append(token)
    return remapped
