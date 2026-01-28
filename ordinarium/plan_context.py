from datetime import date

from .db import get_db
from .liturgical_calendar import resolve_observance_options
from .plan_customizations import load_custom_templates
from .plan_items import build_plan_items
from .plan_lessons import _resolve_lesson_references
from .plan_offertory import (
    _format_offertory_label,
    _load_offertory_sentences,
    _offertory_default_row,
)
from .plan_tokens import parse_plan_tokens, parse_json_object


def build_plan_context(
    service_id,
    rite,
    user_id,
    offertory_default_prefix,
):
    db = get_db()
    saved_plan = db.execute(
        """
        select
          text_order,
          text_disabled,
          title,
          season,
          service_date,
          rite,
          observance_handle,
          lesson_overrides,
          offertory_sentence_id
        from services
        where id=? and user_id=? limit 1
        """,
        (service_id, user_id),
    ).fetchone()
    effective_rite = saved_plan["rite"] if saved_plan and saved_plan["rite"] else rite
    rite_slug = effective_rite.replace(" ", "_").lower()
    order_tokens = parse_plan_tokens(saved_plan["text_order"]) if saved_plan else []
    disabled_tokens = (
        parse_plan_tokens(saved_plan["text_disabled"]) if saved_plan else []
    )
    ordinaries = build_plan_items(
        service_id,
        effective_rite,
        order_tokens,
        disabled_tokens,
        user_id=user_id,
    )
    observance_options = []
    observance_title = ""
    observance_handle = saved_plan["observance_handle"] if saved_plan else None
    lesson_defaults = {}
    if saved_plan and saved_plan["service_date"]:
        try:
            service_date = date.fromisoformat(saved_plan["service_date"])
        except ValueError:
            service_date = None
        if service_date:
            lesson_defaults = _resolve_lesson_references(
                saved_plan["service_date"], observance_handle
            )
            options = resolve_observance_options(service_date)
            if options:
                observance_options = []
                selected_handle = observance_handle
                if selected_handle and not any(
                    option.handle == selected_handle for option in options
                ):
                    selected_handle = None
                if not selected_handle:
                    selected_handle = options[0].handle
                for index, option in enumerate(options):
                    title = option.name or option.alternative_name
                    observance_options.append(
                        {
                            "handle": option.handle,
                            "title": title,
                            "is_default": index == 0,
                            "selected": option.handle == selected_handle,
                        }
                    )
                observance_title = next(
                    (
                        option["title"]
                        for option in observance_options
                        if option["selected"]
                    ),
                    "",
                )

    service_data = {
        "season": saved_plan["season"] if saved_plan else "",
        "service_date": saved_plan["service_date"] if saved_plan else "",
        "rite": effective_rite,
        "title": saved_plan["title"] if saved_plan else "",
    }
    lesson_overrides = parse_json_object(
        saved_plan["lesson_overrides"] if saved_plan else None
    )
    offertory_sentences = _load_offertory_sentences(db, offertory_default_prefix)
    offertory_default = _offertory_default_row(db, offertory_default_prefix)
    offertory_default_label = ""
    if offertory_default:
        offertory_default_label = _format_offertory_label(offertory_default["text"])
    elif offertory_sentences:
        offertory_default_label = offertory_sentences[0]["label"]
    offertory_ids = {sentence["id"] for sentence in offertory_sentences}
    raw_offertory_id = saved_plan["offertory_sentence_id"] if saved_plan else None
    selected_offertory_id = None
    if raw_offertory_id is not None:
        try:
            parsed_id = int(raw_offertory_id)
        except (TypeError, ValueError):
            parsed_id = None
        if parsed_id in offertory_ids:
            selected_offertory_id = parsed_id
    return {
        "rite": effective_rite,
        "rite_slug": rite_slug,
        "ordinaries": ordinaries,
        "service_id": service_id,
        "service": service_data,
        "observance_options": observance_options,
        "observance_title": observance_title,
        "can_delete": bool(saved_plan and saved_plan["service_date"]),
        "can_share": bool(saved_plan and saved_plan["service_date"]),
        "custom_templates": load_custom_templates(user_id),
        "lesson_overrides": lesson_overrides,
        "lesson_defaults": lesson_defaults,
        "offertory_sentences": offertory_sentences,
        "offertory_sentence_id": selected_offertory_id,
        "offertory_default_label": offertory_default_label,
    }
