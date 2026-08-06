import json

from .db import get_database_gateway
from .infrastructure import DatabaseGateway
from .service_defaults import DEFAULT_RITE
from .service_planning import _parse_json_object


def blank_service_payload(user_id, rite=DEFAULT_RITE):
    return {
        "user_id": user_id,
        "title": None,
        "rite": rite,
        "season": None,
        "service_date": None,
        "text_order": None,
        "text_disabled": None,
        "observance_handle": None,
        "lesson_overrides": {},
        "offertory_sentence_id": None,
        "proper_overrides": {},
        "service_option_values": {},
    }


def create_service(db, payload):
    return create_service_record(db, payload)


def create_service_record(gateway: DatabaseGateway, payload):
    serialized = serialize_service_payload(payload)
    service_id = gateway.allocate_id("services")
    gateway.execute(
        """
        insert into services (
          id,
          user_id,
          title,
          rite,
          text_order,
          text_disabled,
          season,
          service_date,
          observance_handle,
          lesson_overrides,
          offertory_sentence_id,
          proper_overrides,
          service_option_values
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            service_id,
            serialized["user_id"],
            serialized["title"],
            serialized["rite"],
            serialized["text_order"],
            serialized["text_disabled"],
            serialized["season"],
            serialized["service_date"],
            serialized["observance_handle"],
            serialized["lesson_overrides"],
            serialized["offertory_sentence_id"],
            serialized["proper_overrides"],
            serialized["service_option_values"],
        ),
    )
    return service_id


def get_service_record(gateway: DatabaseGateway, service_id, user_id=None):
    if not service_id:
        return None
    user_filter = ""
    params = [service_id]
    if user_id:
        user_filter = "and user_id=?"
        params.append(user_id)
    return gateway.fetch_one(
        f"""
        select id, user_id, title, rite, season, service_date,
               observance_handle, updated_at
        from services
        where id=? {user_filter}
        limit 1
        """,
        params,
    )


def serialize_service_payload(payload):
    return {
        "user_id": payload.get("user_id"),
        "title": payload.get("title"),
        "rite": payload.get("rite"),
        "text_order": dump_json_value(payload.get("text_order")),
        "text_disabled": dump_json_value(payload.get("text_disabled")),
        "season": payload.get("season"),
        "service_date": payload.get("service_date"),
        "observance_handle": payload.get("observance_handle"),
        "lesson_overrides": dump_json_value(payload.get("lesson_overrides")),
        "offertory_sentence_id": payload.get("offertory_sentence_id"),
        "proper_overrides": dump_json_value(payload.get("proper_overrides")),
        "service_option_values": dump_json_value(payload.get("service_option_values")),
    }


def load_service_payload(db, service_id, user_id=None):
    if not service_id:
        return None
    query = """
        select
          services.user_id,
          services.title,
          services.rite,
          services.text_order,
          services.text_disabled,
          services.season,
          services.service_date,
          services.observance_handle,
          services.lesson_overrides,
          services.offertory_sentence_id,
          services.proper_overrides,
          services.service_option_values,
          users.default_bible_translation as owner_default_bible_translation,
          users.greeting_response_form as owner_greeting_response_form
        from services
        left join users on users.id=services.user_id
        where services.id=? {user_filter}
        limit 1
        """
    params = [service_id]
    user_filter = ""
    if user_id:
        user_filter = "and services.user_id=?"
        params.append(user_id)
    row = db.fetch_one(query.format(user_filter=user_filter), params)
    if not row:
        return None
    payload = dict(row)
    payload["lesson_overrides"] = _parse_json_object(payload.get("lesson_overrides"))
    payload["proper_overrides"] = _parse_json_object(payload.get("proper_overrides"))
    payload["service_option_values"] = _parse_json_object(
        payload.get("service_option_values")
    )
    return payload


def update_service_columns(db, service_id, payload):
    serialized = serialize_service_payload(payload)
    db.execute(
        """
        update services set
          title=?,
          rite=?,
          text_order=?,
          text_disabled=?,
          season=?,
          service_date=?,
          observance_handle=?,
          lesson_overrides=?,
          offertory_sentence_id=?,
          proper_overrides=?,
          service_option_values=?,
          updated_at=CURRENT_TIMESTAMP
        where id=?
        """,
        (
            serialized["title"],
            serialized["rite"],
            serialized["text_order"],
            serialized["text_disabled"],
            serialized["season"],
            serialized["service_date"],
            serialized["observance_handle"],
            serialized["lesson_overrides"],
            serialized["offertory_sentence_id"],
            serialized["proper_overrides"],
            serialized["service_option_values"],
            service_id,
        ),
    )


def dump_json_value(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def load_service_for_text(service_id, user_id=None):
    if not service_id:
        return None, {}
    db = get_database_gateway()
    if user_id:
        saved_service = db.fetch_one(
            """
            select
              services.user_id,
              services.text_order,
              services.text_disabled,
              services.season,
              services.rite,
              services.service_date,
              services.observance_handle,
              services.lesson_overrides,
              services.offertory_sentence_id,
              services.proper_overrides,
              services.service_option_values,
              users.default_bible_translation as owner_default_bible_translation,
              users.greeting_response_form as owner_greeting_response_form
            from services
            left join users on users.id=services.user_id
            where services.id=? and services.user_id=?
            limit 1
            """,
            (service_id, user_id),
        )
    else:
        saved_service = db.fetch_one(
            """
            select
              services.user_id,
              services.text_order,
              services.text_disabled,
              services.season,
              services.rite,
              services.service_date,
              services.observance_handle,
              services.lesson_overrides,
              services.offertory_sentence_id,
              services.proper_overrides,
              services.service_option_values,
              users.default_bible_translation as owner_default_bible_translation,
              users.greeting_response_form as owner_greeting_response_form
            from services
            left join users on users.id=services.user_id
            where services.id=?
            limit 1
            """,
            (service_id,),
        )
    if not saved_service:
        return None, {}
    saved_data = {
        "owner_user_id": saved_service["user_id"],
        "observance_handle": saved_service["observance_handle"],
        "lesson_overrides": _parse_json_object(saved_service["lesson_overrides"]),
        "offertory_sentence_id": saved_service["offertory_sentence_id"],
        "proper_overrides": _parse_json_object(saved_service["proper_overrides"]),
        "service_option_values": _parse_json_object(
            saved_service["service_option_values"]
        ),
        "default_bible_translation": saved_service["owner_default_bible_translation"],
        "greeting_response_form": saved_service["owner_greeting_response_form"],
    }
    return saved_service, saved_data
