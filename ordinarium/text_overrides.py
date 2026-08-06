import hashlib
import re
from collections import Counter

from .db import get_database_gateway


CUSTOMIZABLE_TEXT_TYPES = frozenset(
    {
        "acclamation",
        "law_form",
        "offertory_sentence",
        "ordinarium",
        "proper_preface",
    }
)
_JINJA_TOKEN_PATTERN = re.compile(r"{[{%#]")
_CANONICAL_SLOT_PATTERN = re.compile(
    r"{{\s*([a-z][a-z0-9_]*)\s*(?:\|\s*markdown\s*)?}}"
)
_HOUSE_USE_SLOT_PATTERN = re.compile(r"\[\[([^\[\]]+)]]")

HOUSE_USE_SLOT_LABELS = {
    "acclamation": "Acclamation text",
    "collect_of_the_day": "Collect of the Day",
    "lesson_1_reference": "First lesson reference",
    "psalm_reference": "Psalm reference",
    "lesson_2_reference": "Second lesson reference",
    "gospel_reference": "Gospel reference",
    "offertory_sentence": "Offertory sentence",
    "proper_preface": "Proper preface",
}
_HOUSE_USE_SLOT_KEYS = {
    label.casefold(): key for key, label in HOUSE_USE_SLOT_LABELS.items()
}


class HouseUseText(str):
    """Markdown carrying user-authored house-use provenance through Jinja."""


def mark_house_use_text(value):
    return HouseUseText(value or "")


def is_house_use_text(value):
    return isinstance(value, HouseUseText)


class TextOverrideValidationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def canonical_text_hash(text):
    value = text if text is not None else ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def contains_jinja_tokens(text):
    return bool(_JINJA_TOKEN_PATTERN.search(text or ""))


def house_use_slot_token(slot_key):
    return f"[[{HOUSE_USE_SLOT_LABELS[slot_key]}]]"


def canonical_template_slots(text):
    value = text or ""
    matches = list(_CANONICAL_SLOT_PATTERN.finditer(value))
    if not matches:
        return () if not contains_jinja_tokens(value) else None
    remaining = _CANONICAL_SLOT_PATTERN.sub("", value)
    slot_keys = tuple(match.group(1) for match in matches)
    if contains_jinja_tokens(remaining):
        return None
    if any(slot_key not in HOUSE_USE_SLOT_LABELS for slot_key in slot_keys):
        return None
    return slot_keys


def canonical_text_for_house_use(text):
    slots = canonical_template_slots(text)
    if not slots:
        return text or ""
    return _CANONICAL_SLOT_PATTERN.sub(
        lambda match: house_use_slot_token(match.group(1)), text or ""
    )


def house_use_slot_keys(text):
    slot_keys = []
    for match in _HOUSE_USE_SLOT_PATTERN.finditer(text or ""):
        slot_key = _HOUSE_USE_SLOT_KEYS.get(match.group(1).strip().casefold())
        if slot_key:
            slot_keys.append(slot_key)
    return tuple(slot_keys)


def render_house_use_slots(text, context):
    def replace_slot(match):
        slot_key = _HOUSE_USE_SLOT_KEYS.get(match.group(1).strip().casefold())
        if not slot_key:
            return match.group(0)
        return str(context.get(slot_key) or "")

    return _HOUSE_USE_SLOT_PATTERN.sub(replace_slot, text or "")


def load_customizable_texts():
    placeholders = ", ".join("?" for _ in CUSTOMIZABLE_TEXT_TYPES)
    rows = get_database_gateway().fetch_all(
        f"""
        select id, type, filter_type, filter_content, text, title,
               detailed_title, default_order
        from texts
        where type in ({placeholders})
        order by type, filter_type, filter_content, default_order, id
        """,
        tuple(sorted(CUSTOMIZABLE_TEXT_TYPES)),
    )
    return [
        row for row in rows if canonical_template_slots(row.get("text")) is not None
    ]


def load_user_text_overrides(user_id):
    rows = get_database_gateway().fetch_all(
        """
        select overrides.user_id,
               overrides.text_id,
               overrides.replacement_text,
               overrides.base_text_hash,
               overrides.created_at,
               overrides.updated_at,
               texts.type as canonical_type,
               texts.text as canonical_text,
               texts.title as canonical_title,
               texts.detailed_title as canonical_detailed_title,
               texts.filter_type as canonical_filter_type,
               texts.filter_content as canonical_filter_content,
               texts.default_order as canonical_default_order
        from user_text_overrides overrides
        join texts on texts.id=overrides.text_id
        where overrides.user_id=?
        order by overrides.text_id
        """,
        (user_id,),
    )
    return {row["text_id"]: _with_stale_state(row) for row in rows}


def upsert_user_text_override(user_id, text_id, replacement_text):
    canonical = _load_canonical_text(text_id)
    _validate_canonical_text(canonical)
    if not isinstance(replacement_text, str):
        raise TextOverrideValidationError(
            "replacement_text_invalid", "Replacement text must be a string."
        )
    _validate_replacement_slots(canonical.get("text"), replacement_text)

    get_database_gateway().execute(
        """
        insert into user_text_overrides (
          user_id, text_id, replacement_text, base_text_hash
        ) values (?, ?, ?, ?)
        on conflict(user_id, text_id) do update set
          replacement_text=excluded.replacement_text,
          base_text_hash=excluded.base_text_hash,
          updated_at=CURRENT_TIMESTAMP
        """,
        (
            user_id,
            canonical["id"],
            replacement_text,
            canonical_text_hash(canonical.get("text")),
        ),
    )


def acknowledge_user_text_override(user_id, text_id, expected_current_text_hash):
    override = get_database_gateway().fetch_one(
        """
        select overrides.base_text_hash, texts.text as canonical_text
        from user_text_overrides overrides
        join texts on texts.id=overrides.text_id
        where overrides.user_id=? and overrides.text_id=?
        limit 1
        """,
        (user_id, text_id),
    )
    if override is None:
        raise TextOverrideValidationError(
            "text_override_not_found", "House use was not found."
        )
    if not isinstance(expected_current_text_hash, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_current_text_hash
    ):
        raise TextOverrideValidationError(
            "current_text_hash_invalid", "Official text version is required."
        )

    current_hash = canonical_text_hash(override.get("canonical_text"))
    if current_hash != expected_current_text_hash:
        raise TextOverrideValidationError(
            "canonical_text_changed_again",
            "Official text changed again. Review the latest version before acknowledging.",
        )
    if override["base_text_hash"] == current_hash:
        raise TextOverrideValidationError(
            "text_override_not_stale", "This house use is already up to date."
        )

    get_database_gateway().execute(
        """
        update user_text_overrides
        set base_text_hash=?, updated_at=CURRENT_TIMESTAMP
        where user_id=? and text_id=?
        """,
        (current_hash, user_id, text_id),
    )


def delete_user_text_override(user_id, text_id):
    result = get_database_gateway().execute(
        "delete from user_text_overrides where user_id=? and text_id=?",
        (user_id, text_id),
    )
    return result.changes > 0


def resolve_text_override(canonical_text, overrides_by_text_id):
    resolved = dict(canonical_text)
    resolved["canonical_text"] = canonical_text.get("text")
    resolved["house_use_slots"] = (
        canonical_template_slots(canonical_text.get("text")) or ()
    )
    override = overrides_by_text_id.get(canonical_text["id"])
    resolved["house_use_applied"] = override is not None
    resolved["house_use_stale"] = False
    if override is None:
        return resolved
    resolved["text"] = override["replacement_text"]
    resolved["house_use_stale"] = bool(override.get("is_stale"))
    return resolved


def _load_canonical_text(text_id):
    row = get_database_gateway().fetch_one(
        """
        select id, type, filter_type, filter_content, text, title,
               detailed_title, default_order
        from texts
        where id=?
        limit 1
        """,
        (text_id,),
    )
    if row is None:
        raise TextOverrideValidationError(
            "canonical_text_not_found", "Official text was not found."
        )
    return row


def _validate_canonical_text(canonical):
    if canonical["type"] not in CUSTOMIZABLE_TEXT_TYPES:
        raise TextOverrideValidationError(
            "text_type_not_customizable",
            "This type of official text cannot be customized.",
        )
    if canonical_template_slots(canonical.get("text")) is None:
        raise TextOverrideValidationError(
            "templated_text_not_customizable",
            "This official template uses unsupported dynamic logic and cannot be customized.",
        )


def _validate_replacement_slots(canonical_text, replacement_text):
    canonical_slots = canonical_template_slots(canonical_text)
    if not canonical_slots:
        return
    raw_labels = [
        match.group(1).strip()
        for match in _HOUSE_USE_SLOT_PATTERN.finditer(replacement_text)
    ]
    unknown_labels = [
        label for label in raw_labels if label.casefold() not in _HOUSE_USE_SLOT_KEYS
    ]
    if unknown_labels:
        raise TextOverrideValidationError(
            "house_use_slot_unknown",
            f"Unknown dynamic slot: [[{unknown_labels[0]}]].",
        )
    replacement_slots = house_use_slot_keys(replacement_text)
    if Counter(replacement_slots) == Counter(canonical_slots):
        return
    expected = ", ".join(house_use_slot_token(key) for key in canonical_slots)
    raise TextOverrideValidationError(
        "house_use_slots_invalid",
        f"Keep each required dynamic slot exactly once: {expected}.",
    )


def _with_stale_state(row):
    value = dict(row)
    current_hash = canonical_text_hash(value.get("canonical_text"))
    value["current_text_hash"] = current_hash
    value["is_stale"] = value["base_text_hash"] != current_hash
    return value
