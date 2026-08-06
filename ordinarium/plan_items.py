from .db import get_database_gateway
from .plan_customizations import load_custom_elements
from .text_overrides import (
    house_use_slot_keys,
    load_user_text_overrides,
    resolve_text_override,
)


_SUPPORTING_FRAGMENT_TYPES = {
    "acclamation": "acclamation",
    "decalogue_text": "law_form",
    "offertory_sentence": "offertory_sentence",
    "proper_preface": "proper_preface",
}


def build_plan_items(
    service_id,
    rite,
    order_tokens,
    disabled_tokens,
    user_id=None,
    overrides_by_text_id=None,
):
    db = get_database_gateway()
    text_rows = db.fetch_all(
        "select id, type, default_order, title, detailed_title, text from texts where type=? and filter_type=? and filter_content=? order by default_order",
        ("ordinarium", "rite", rite),
    )
    if overrides_by_text_id is None:
        overrides_by_text_id = (
            load_user_text_overrides(user_id) if user_id is not None else {}
        )
    text_items = []
    items_by_token = {}
    overridden_supporting_types = {
        override.get("canonical_type") for override in overrides_by_text_id.values()
    }
    for row in text_rows:
        row = resolve_text_override(row, overrides_by_text_id)
        canonical_source = row.get("canonical_text") or ""
        replacement_slots = set(house_use_slot_keys(row.get("text")))
        supporting_fragments = sorted(
            variable
            for variable, text_type in _SUPPORTING_FRAGMENT_TYPES.items()
            if text_type in overridden_supporting_types
            and (
                f"{{{{ {variable}" in canonical_source or variable in replacement_slots
            )
        )
        token = f"text:{row['id']}"
        item = {
            "id": row["id"],
            "token": token,
            "type": "text",
            "canonical_type": row["type"],
            "title": row["title"],
            "detailed_title": row["detailed_title"],
            "text": row["text"],
            "default_order": row["default_order"] or 0,
            "house_use_applied": row["house_use_applied"],
            "house_use_stale": row["house_use_stale"],
            "house_use_slots": row.get("house_use_slots") or (),
            "house_use_supporting_configured": bool(supporting_fragments),
            "house_use_supporting_fragments": supporting_fragments,
        }
        text_items.append(item)
        items_by_token[token] = item

    custom_items = []
    for row in load_custom_elements(service_id, user_id=user_id):
        token = f"custom:{row['id']}"
        item = {
            "id": row["id"],
            "token": token,
            "type": "custom",
            "title": row["title"],
            "detailed_title": None,
            "text": row["text"],
            "default_order": None,
            "created_at": row["created_at"],
        }
        custom_items.append(item)
        items_by_token[token] = item

    used = set()
    ordered_items = []
    disabled_set = set(disabled_tokens or [])

    def append_item(token):
        item = items_by_token.get(token)
        if not item or token in used:
            return
        output = dict(item)
        output["disabled"] = token in disabled_set
        ordered_items.append(output)
        used.add(token)

    if order_tokens:
        for token in order_tokens:
            append_item(token)
    text_items_sorted = sorted(text_items, key=lambda item: item["default_order"] or 0)
    custom_items_sorted = sorted(
        custom_items,
        key=lambda item: (item.get("created_at") or "", item["id"]),
    )
    if order_tokens:
        for item in text_items_sorted:
            append_item(item["token"])
        for item in custom_items_sorted:
            append_item(item["token"])
    else:
        for item in text_items_sorted + custom_items_sorted:
            append_item(item["token"])

    return ordered_items
