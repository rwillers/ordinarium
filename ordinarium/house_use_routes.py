from collections import OrderedDict
import re

from flask import flash, g, redirect, render_template, request, url_for

from .auth_session import login_required
from .error_pages import render_error
from .text_overrides import (
    HOUSE_USE_SLOT_LABELS,
    TextOverrideValidationError,
    acknowledge_user_text_override,
    canonical_template_slots,
    canonical_text_for_house_use,
    delete_user_text_override,
    house_use_slot_token,
    load_customizable_texts,
    load_user_text_overrides,
    upsert_user_text_override,
)


TEXT_TYPE_LABELS = {
    "acclamation": "Acclamation",
    "law_form": "Law form",
    "offertory_sentence": "Offertory sentence",
    "ordinarium": "Service text",
    "proper_preface": "Proper preface",
}

SOURCE_GROUPS = {
    "acclamation": (
        "supporting-acclamations",
        "Seasonal and occasional acclamations",
    ),
    "offertory_sentence": ("supporting-offertory", "Offertory sentences"),
    "proper_preface": ("supporting-prefaces", "Proper prefaces"),
}

RITE_SECTION_BANDS = (
    (100, "opening", "Opening"),
    (180, "word-prayers", "Word and prayers"),
    (270, "holy-communion", "Holy Communion"),
    (float("inf"), "conclusion", "Conclusion"),
)


def register_house_use_routes(bp):
    @bp.get("/house-uses")
    @login_required
    def house_uses():
        overrides = load_user_text_overrides(g.user["id"])
        rows = _include_existing_override_rows(load_customizable_texts(), overrides)
        groups = _group_customizable_texts(rows, overrides)
        filter_options = _build_filter_options(groups, len(overrides))
        selected_filter = _resolve_filter(
            request.args.get("group"),
            filter_options,
            g.user.default_rite,
            has_overrides=bool(overrides),
        )
        filtered_groups = _filter_groups(groups, selected_filter)
        return render_template(
            "house_uses.html",
            house_use_groups=filtered_groups,
            house_use_filter_options=filter_options,
            selected_house_use_filter=selected_filter,
            has_customizable_texts=bool(groups),
        )

    @bp.post("/house-uses/<int:text_id>/save")
    @login_required
    def house_use_save(text_id):
        if "replacement_text" not in request.form:
            return render_error("House-use text is required.", 400)
        try:
            upsert_user_text_override(
                g.user["id"], text_id, request.form["replacement_text"]
            )
        except TextOverrideValidationError as error:
            return _render_validation_error(error)
        flash("House use saved.", "success")
        return _house_use_redirect(text_id)

    @bp.post("/house-uses/<int:text_id>/restore")
    @login_required
    def house_use_restore(text_id):
        if not delete_user_text_override(g.user["id"], text_id):
            return render_error("House use not found.", 404)
        flash("Official text restored.", "success")
        return _house_use_redirect(text_id)

    @bp.post("/house-uses/<int:text_id>/review")
    @login_required
    def house_use_review(text_id):
        try:
            acknowledge_user_text_override(
                g.user["id"],
                text_id,
                request.form.get("current_text_hash"),
            )
        except TextOverrideValidationError as error:
            return _render_validation_error(error)
        flash("Official text review acknowledged.", "success")
        return _house_use_redirect(text_id)


def _group_customizable_texts(rows, overrides):
    groups = OrderedDict()
    for row in sorted(rows, key=_text_sort_key):
        group_key, group_label, group_order = _group_identity(row)
        group = groups.setdefault(
            group_key,
            {
                "key": group_key,
                "label": group_label,
                "order": group_order,
                "filter_key": _group_filter_key(row),
                "items": [],
            },
        )
        override = overrides.get(row["id"])
        group["items"].append(_present_text(row, override))
    return sorted(groups.values(), key=lambda group: group["order"])


def _group_identity(row):
    if row.get("filter_type") == "rite" and row.get("filter_content"):
        rite = row["filter_content"]
        band_index, band_key, band_label = _rite_section(row.get("default_order"))
        return (
            f"rite-{rite}-{band_key}",
            f"{rite} — {band_label}",
            (0, rite, band_index),
        )
    if row["type"] in SOURCE_GROUPS:
        group_key, group_label = SOURCE_GROUPS[row["type"]]
        source_order = tuple(SOURCE_GROUPS).index(row["type"])
        return group_key, group_label, (2, source_order, 0)
    return "other-liturgies", "Other liturgies and offices", (1, "", 0)


def _present_text(row, override):
    item = dict(row)
    official_text = row.get("text") or ""
    slots = canonical_template_slots(official_text)
    item["type_label"] = TEXT_TYPE_LABELS.get(
        row["type"], row["type"].replace("_", " ").title()
    )
    item["display_label"] = _text_label(row)
    item["has_override"] = override is not None
    item["is_stale"] = bool(override and override["is_stale"])
    item["current_text_hash"] = override.get("current_text_hash") if override else None
    item["is_locked"] = bool(row.get("is_locked"))
    item["official_display_text"] = canonical_text_for_house_use(official_text)
    item["dynamic_slots"] = [
        {
            "key": key,
            "label": HOUSE_USE_SLOT_LABELS[key],
            "token": house_use_slot_token(key),
        }
        for key in dict.fromkeys(slots or ())
    ]
    item["replacement_text"] = (
        override["replacement_text"]
        if override
        else canonical_text_for_house_use(official_text)
    )
    return item


def _build_filter_options(groups, override_count):
    options = [
        {
            "value": "customized",
            "label": "Currently customized",
            "count": override_count,
        }
    ]
    grouped = OrderedDict()
    for group in groups:
        entry = grouped.setdefault(
            group["filter_key"],
            {
                "value": group["filter_key"],
                "label": _filter_label(group),
                "count": 0,
            },
        )
        entry["count"] += len(group["items"])
    options.extend(grouped.values())
    options.append(
        {
            "value": "all",
            "label": "All house-use texts",
            "count": sum(len(group["items"]) for group in groups),
        }
    )
    return options


def _resolve_filter(requested, options, default_rite, has_overrides):
    valid_values = {option["value"] for option in options}
    if requested in valid_values:
        return requested
    if has_overrides:
        return "customized"
    default_rite_filter = f"rite-{_slugify(default_rite)}"
    if default_rite_filter in valid_values:
        return default_rite_filter
    return "all"


def _filter_groups(groups, selected_filter):
    if selected_filter == "all":
        return groups
    if selected_filter == "customized":
        filtered = []
        for group in groups:
            items = [item for item in group["items"] if item["has_override"]]
            if items:
                filtered.append({**group, "items": items})
        return filtered
    return [group for group in groups if group["filter_key"] == selected_filter]


def _filter_label(group):
    if group["filter_key"].startswith("rite-"):
        return group["label"].split(" — ", 1)[0]
    return {
        "acclamations": "Acclamations",
        "offertory-sentences": "Offertory sentences",
        "proper-prefaces": "Proper prefaces",
        "other": "Other liturgies and offices",
    }.get(group["filter_key"], group["label"])


def _group_filter_key(row):
    if row.get("filter_type") == "rite" and row.get("filter_content"):
        return f"rite-{_slugify(row['filter_content'])}"
    return {
        "acclamation": "acclamations",
        "offertory_sentence": "offertory-sentences",
        "proper_preface": "proper-prefaces",
    }.get(row["type"], "other")


def _slugify(value):
    return re.sub(r"[^a-z0-9]+", "-", (value or "").casefold()).strip("-")


def _house_use_redirect(text_id):
    return_group = (request.form.get("return_group") or "").strip()
    route_values = {"_anchor": f"text-{text_id}"}
    if return_group:
        route_values["group"] = return_group
    return redirect(url_for("main.house_uses", **route_values))


def _text_label(row):
    if row.get("title"):
        return row["title"]
    if row.get("filter_content"):
        return row["filter_content"]
    return f"{TEXT_TYPE_LABELS.get(row['type'], 'Text')} {row['id']}"


def _render_validation_error(error):
    if error.code in {"canonical_text_not_found", "text_override_not_found"}:
        status_code = 404
    elif error.code in {"canonical_text_changed_again", "text_override_not_stale"}:
        status_code = 409
    else:
        status_code = 400
    return render_error(str(error), status_code)


def _include_existing_override_rows(rows, overrides):
    visible_ids = {row["id"] for row in rows}
    combined = [dict(row, is_locked=False) for row in rows]
    for text_id, override in overrides.items():
        if text_id in visible_ids:
            continue
        combined.append(
            {
                "id": text_id,
                "type": override["canonical_type"],
                "filter_type": override["canonical_filter_type"],
                "filter_content": override["canonical_filter_content"],
                "text": override["canonical_text"],
                "title": override["canonical_title"],
                "detailed_title": override["canonical_detailed_title"],
                "default_order": override["canonical_default_order"],
                "is_locked": True,
            }
        )
    return combined


def _rite_section(default_order):
    order = default_order if isinstance(default_order, (int, float)) else 0
    for index, (upper_bound, key, label) in enumerate(RITE_SECTION_BANDS):
        if order < upper_bound:
            return index, key, label
    raise AssertionError("Rite section bands must end with an infinite upper bound.")


def _text_sort_key(row):
    _group_key, _group_label, group_order = _group_identity(row)
    return (
        group_order,
        row.get("default_order") if row.get("default_order") is not None else 0,
        row.get("filter_content") or "",
        row["id"],
    )
