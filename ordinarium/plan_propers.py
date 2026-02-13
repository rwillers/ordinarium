import json
import re
from functools import lru_cache

from .liturgical_data import _load_holidays


PROPER_OVERRIDE_TYPES = {
    "collect_of_the_day": "collect",
    "proper_preface": "proper_preface",
}


def _first_content_line(text):
    if not text:
        return ""
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("######"):
            continue
        return cleaned
    return ""


def _format_option_label(prefix, text, limit=110):
    excerpt = _first_content_line(text)
    if len(excerpt) > limit:
        excerpt = excerpt[: max(limit - 3, 0)].rstrip() + "..."
    if prefix and excerpt:
        return f"{prefix}: {excerpt}"
    return prefix or excerpt


def _parse_override_id(value):
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


@lru_cache(maxsize=1)
def _collect_proper_labels():
    labels = {}
    for holiday in _load_holidays():
        display_name = holiday.get("name") or holiday.get("alternative_name") or ""
        if not display_name:
            continue
        for proper in holiday.get("propers") or []:
            if not proper:
                continue
            existing = labels.get(proper)
            if not existing:
                labels[proper] = [display_name]
                continue
            if display_name not in existing:
                existing.append(display_name)
    return {proper: " / ".join(names) for proper, names in labels.items() if names}


@lru_cache(maxsize=1)
def _collect_proper_church_order():
    order = {}
    rank = 0
    for holiday in _load_holidays():
        for proper in holiday.get("propers") or []:
            if not proper or proper in order:
                continue
            order[proper] = rank
            rank += 1
    return order


def _humanize_proper_handle(handle):
    if not handle:
        return ""
    match = re.fullmatch(r"Proper(\d+)", handle)
    if match:
        return f"Proper {match.group(1)}"
    value = re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", handle)
    value = re.sub(r"(?<=[0-9])(?=[A-Za-z])", " ", value)
    parts = [part for part in value.split() if part]
    if not parts:
        return handle
    small_words = {"Of", "The", "And", "Or", "In", "After", "Any"}
    normalized = []
    for index, part in enumerate(parts):
        if index > 0 and part in small_words:
            normalized.append(part.lower())
            continue
        normalized.append(part)
    return " ".join(normalized)


def _display_collect_proper_label(proper_handle):
    labels = _collect_proper_labels()
    if proper_handle in labels:
        return labels[proper_handle]
    return _humanize_proper_handle(proper_handle)


def _natural_sort_key(value):
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", (value or "").lower())
    ]


def _collect_option_sort_key(row):
    handle = row["filter_content"] or ""
    church_order = _collect_proper_church_order()
    church_rank = church_order.get(handle)
    default_order = row["default_order"] or 0
    if church_rank is not None:
        return (0, church_rank, default_order, row["id"])
    label = _display_collect_proper_label(handle)
    return (1, _natural_sort_key(label), default_order, row["id"])


def _resolve_proper_override(db, proper_overrides, proper_key):
    if not isinstance(proper_overrides, dict):
        return None
    text_type = PROPER_OVERRIDE_TYPES.get(proper_key)
    if not text_type:
        return None
    text_id = _parse_override_id(proper_overrides.get(proper_key))
    if not text_id:
        return None
    return db.execute(
        "select id, text from texts where id=? and type=? limit 1",
        (text_id, text_type),
    ).fetchone()


def _load_collect_options(db):
    rows = db.execute(
        """
        select id, filter_content, text, default_order
        from texts
        where type=? and filter_type=?
        order by id
        """,
        ("collect", "proper"),
    ).fetchall()
    sorted_rows = sorted(rows, key=_collect_option_sort_key)
    return [
        {
            "id": row["id"],
            "label": _format_option_label(
                _display_collect_proper_label(row["filter_content"] or ""),
                row["text"] or "",
            ),
        }
        for row in sorted_rows
    ]


def _load_proper_preface_options(db):
    rows = db.execute(
        """
        select id, filter_type, filter_content, text
        from texts
        where type=?
        order by filter_type, filter_content, id
        """,
        ("proper_preface",),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "label": _format_option_label(
                f"{(row['filter_type'] or 'other').replace('_', ' ').title()} - {row['filter_content'] or 'Unlabeled'}",
                row["text"] or "",
            ),
        }
        for row in rows
    ]


def _resolve_seasonal_text(db, text_type, season):
    row = None
    if season:
        row = db.execute(
            "select text from texts where type=? and filter_type=? and filter_content=? order by random() limit 1",
            (text_type, "season", season),
        ).fetchone()
    if not row:
        row = db.execute(
            "select text from texts where type=? and ((filter_type=? and filter_content=?) or (filter_type=? and filter_content=?)) order by random() limit 1",
            (text_type, "other", "At Any Time", "day", "The Lord’s Day"),
        ).fetchone()
    return row["text"] if row else None


def _resolve_collect_text(db, propers_list):
    if not propers_list:
        return None
    propers_json = json.dumps(propers_list)
    collect_text = db.execute(
        "select texts.text from texts join json_each(?) propers on texts.filter_content=propers.value where texts.type=? and texts.filter_type=? order by propers.key, texts.default_order limit 1",
        (propers_json, "collect", "proper"),
    ).fetchone()
    return collect_text["text"] if collect_text else None
