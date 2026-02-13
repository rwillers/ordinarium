import json
from datetime import date, datetime

from flask import current_app, render_template, request

from .db import get_db
from .error_pages import render_error
from .liturgical_calendar import resolve_observance
from .service_defaults import OFFERTORY_DEFAULT_PREFIX
from .service_planning import (
    build_plan_items,
    parse_plan_tokens,
    _build_lesson_readings,
    _format_lesson_reference,
    _resolve_offertory_sentence,
    _resolve_proper_override,
)


def render_text_page(service_id, saved_service, saved_data, user_id=None):
    if not saved_service:
        return render_error("Service ID required to generate text.", 400)
    db = get_db()
    text_cache = {}

    def fetch_text(text_type, filter_type, filter_content, random_choice=False):
        key = (text_type, filter_type, filter_content)
        if key in text_cache:
            return text_cache[key]
        order_clause = "order by random()" if random_choice else ""
        row = db.execute(
            f"select text from texts where type=? and filter_type=? and filter_content=? {order_clause} limit 1",
            (text_type, filter_type, filter_content),
        ).fetchone()
        text_cache[key] = row
        return row

    title = "The Holy Eucharist"

    if not saved_service["rite"]:
        return render_error("Service rite is required to generate text.", 400)
    rite_name = saved_service["rite"]
    rite = fetch_text("ordinarium", "rite", rite_name)
    if not rite:
        return render_error("Rite not found.", 404)

    order_tokens = parse_plan_tokens(saved_service["text_order"])
    disabled_tokens = parse_plan_tokens(saved_service["text_disabled"])
    plan_items = build_plan_items(
        service_id,
        rite_name,
        order_tokens,
        disabled_tokens,
        user_id=user_id,
    )
    ordinaries = [
        {"title": item["title"], "text": item["text"], "type": item.get("type")}
        for item in plan_items
        if not item.get("disabled")
    ]
    if not ordinaries:
        return render_error("Content not found.", 404)

    season = request.args.get("season", "")
    if service_id:
        if saved_service and saved_service["season"]:
            season = saved_service["season"]

    acclamation = None
    if season:
        acclamation = fetch_text("acclamation", "season", season, random_choice=True)
    if not acclamation:
        acclamation = db.execute(
            "select text from texts where type=? and ((filter_type=? and filter_content=?) or (filter_type=? and filter_content=?)) order by random() limit 1",
            ("acclamation", "other", "At Any Time", "day", "The Lord’s Day"),
        ).fetchone()
    offertory_sentence = _resolve_offertory_sentence(
        db, OFFERTORY_DEFAULT_PREFIX, saved_data.get("offertory_sentence_id")
    )
    proper_preface = None
    if season:
        proper_preface = fetch_text(
            "proper_preface", "season", season, random_choice=True
        )
    if not proper_preface:
        proper_preface = db.execute(
            "select text from texts where type=? and ((filter_type=? and filter_content=?) or (filter_type=? and filter_content=?)) order by random() limit 1",
            ("proper_preface", "other", "At Any Time", "day", "The Lord’s Day"),
        ).fetchone()
    observance = None
    propers_list = []
    if saved_service and saved_service["service_date"]:
        try:
            observance = resolve_observance(
                date.fromisoformat(saved_service["service_date"]),
                saved_data.get("observance_handle"),
            )
        except ValueError:
            observance = None
    if observance:
        propers_list = list(observance.propers)

    collect_text = None
    if propers_list:
        propers_json = json.dumps(propers_list)
        collect_text = db.execute(
            "select texts.text from texts join json_each(?) propers on texts.filter_content=propers.value where texts.type=? and texts.filter_type=? order by propers.key, texts.default_order limit 1",
            (propers_json, "collect", "proper"),
        ).fetchone()
    proper_overrides = saved_data.get("proper_overrides")
    collect_override = _resolve_proper_override(
        db, proper_overrides, "collect_of_the_day"
    )
    if collect_override:
        collect_text = collect_override
    preface_override = _resolve_proper_override(db, proper_overrides, "proper_preface")
    if preface_override:
        proper_preface = preface_override

    subcycle = observance.subcycle if observance else None
    readings = _build_lesson_readings(propers_list, subcycle)
    lesson_defaults = {
        "lesson_1_reference": _format_lesson_reference(readings.get(1)),
        "psalm_reference": _format_lesson_reference(readings.get(2)),
        "lesson_2_reference": _format_lesson_reference(readings.get(3)),
        "gospel_reference": _format_lesson_reference(readings.get(5)),
    }

    propers = {
        "acclamation": (
            acclamation["text"] if acclamation else "*Error: No acclamation found.*"
        ),
        "collect_of_the_day": (
            collect_text["text"]
            if collect_text
            else "*Error: No collect found for this date.*"
        ),
        "lesson_1_reference": lesson_defaults.get("lesson_1_reference")
        or "*Error: No first lesson found.*",
        "psalm_reference": lesson_defaults.get("psalm_reference")
        or "*Error: No psalm found.*",
        "lesson_2_reference": lesson_defaults.get("lesson_2_reference")
        or "*Error: No second lesson found.*",
        "gospel_reference": lesson_defaults.get("gospel_reference")
        or "*Error: No gospel found.*",
        "offertory_sentence": (
            offertory_sentence["text"]
            if offertory_sentence
            else "*Error: No offertory sentence found.*"
        ),
        "proper_preface": (
            proper_preface["text"]
            if proper_preface
            else "*Error: No proper preface found.*"
        ),
    }
    lesson_overrides = saved_data.get("lesson_overrides")
    if not isinstance(lesson_overrides, dict):
        lesson_overrides = {}
    override_map = {
        "lesson_1": "lesson_1_reference",
        "psalm": "psalm_reference",
        "lesson_2": "lesson_2_reference",
        "gospel": "gospel_reference",
    }
    for override_key, prop_key in override_map.items():
        custom_value = lesson_overrides.get(override_key)
        if custom_value:
            propers[prop_key] = custom_value
    service_title = (
        (observance.name or observance.alternative_name) if observance else ""
    )
    service_date_display = ""
    if saved_service and saved_service["service_date"]:
        try:
            parsed_date = date.fromisoformat(saved_service["service_date"])
            service_date_display = (
                f"{parsed_date.strftime('%B')} {parsed_date.day}, {parsed_date.year}"
            )
        except ValueError:
            service_date_display = ""
    generated_at = datetime.now()
    generated_at_display = (
        f"{generated_at.strftime('%B')} {generated_at.day}, {generated_at.year} "
        f"at {generated_at.strftime('%I:%M %p').lstrip('0')}"
    )
    return render_template(
        "text.html",
        service_id=service_id,
        allow_export=bool(user_id),
        title=title,
        rite=rite_name,
        service_title=service_title,
        service_date_display=service_date_display,
        generated_at_display=generated_at_display,
        ordinaries=ordinaries,
        **propers,
    )


def build_rendered_ordinaries(
    service_id, saved_service, saved_data, user_id=None, include_metadata=False
):
    if not saved_service:
        return None
    if not isinstance(saved_service, dict):
        saved_service = dict(saved_service)
    if not saved_service.get("rite"):
        return None
    db = get_db()
    text_cache = {}

    def fetch_text(text_type, filter_type, filter_content, random_choice=False):
        key = (text_type, filter_type, filter_content)
        if key in text_cache:
            return text_cache[key]
        order_clause = "order by random()" if random_choice else ""
        row = db.execute(
            f"select text from texts where type=? and filter_type=? and filter_content=? {order_clause} limit 1",
            (text_type, filter_type, filter_content),
        ).fetchone()
        text_cache[key] = row
        return row

    def render_template_text(value, context):
        if not value:
            return ""
        template = current_app.jinja_env.from_string(value)
        return template.render(context)

    title = "The Holy Eucharist"
    rite_name = saved_service["rite"]
    rite = fetch_text("ordinarium", "rite", rite_name)
    if not rite:
        return None

    order_tokens = parse_plan_tokens(saved_service.get("text_order"))
    disabled_tokens = parse_plan_tokens(saved_service.get("text_disabled"))
    plan_items = build_plan_items(
        service_id,
        rite_name,
        order_tokens,
        disabled_tokens,
        user_id=user_id,
    )
    ordinaries = [
        {
            "title": item.get("title"),
            "text": item.get("text"),
            "type": item.get("type"),
        }
        for item in plan_items
        if not item.get("disabled")
    ]
    if not ordinaries:
        return None

    season = saved_service.get("season") or ""

    acclamation = None
    if season:
        acclamation = fetch_text("acclamation", "season", season, random_choice=True)
    if not acclamation:
        acclamation = db.execute(
            "select text from texts where type=? and ((filter_type=? and filter_content=?) or (filter_type=? and filter_content=?)) order by random() limit 1",
            ("acclamation", "other", "At Any Time", "day", "The Lord’s Day"),
        ).fetchone()
    offertory_sentence = _resolve_offertory_sentence(
        db, OFFERTORY_DEFAULT_PREFIX, saved_data.get("offertory_sentence_id")
    )
    proper_preface = None
    if season:
        proper_preface = fetch_text(
            "proper_preface", "season", season, random_choice=True
        )
    if not proper_preface:
        proper_preface = db.execute(
            "select text from texts where type=? and ((filter_type=? and filter_content=?) or (filter_type=? and filter_content=?)) order by random() limit 1",
            ("proper_preface", "other", "At Any Time", "day", "The Lord’s Day"),
        ).fetchone()

    observance = None
    propers_list = []
    if saved_service and saved_service.get("service_date"):
        try:
            observance = resolve_observance(
                date.fromisoformat(saved_service["service_date"]),
                saved_data.get("observance_handle"),
            )
        except ValueError:
            observance = None
    if observance:
        propers_list = list(observance.propers)

    collect_text = None
    if propers_list:
        propers_json = json.dumps(propers_list)
        collect_text = db.execute(
            "select texts.text from texts join json_each(?) propers on texts.filter_content=propers.value where texts.type=? and texts.filter_type=? order by propers.key, texts.default_order limit 1",
            (propers_json, "collect", "proper"),
        ).fetchone()
    proper_overrides = saved_data.get("proper_overrides")
    collect_override = _resolve_proper_override(
        db, proper_overrides, "collect_of_the_day"
    )
    if collect_override:
        collect_text = collect_override
    preface_override = _resolve_proper_override(db, proper_overrides, "proper_preface")
    if preface_override:
        proper_preface = preface_override

    subcycle = observance.subcycle if observance else None
    readings = _build_lesson_readings(propers_list, subcycle)
    lesson_defaults = {
        "lesson_1_reference": _format_lesson_reference(readings.get(1)),
        "psalm_reference": _format_lesson_reference(readings.get(2)),
        "lesson_2_reference": _format_lesson_reference(readings.get(3)),
        "gospel_reference": _format_lesson_reference(readings.get(5)),
    }

    propers = {
        "acclamation": (
            acclamation["text"] if acclamation else "*Error: No acclamation found.*"
        ),
        "collect_of_the_day": (
            collect_text["text"]
            if collect_text
            else "*Error: No collect found for this date.*"
        ),
        "lesson_1_reference": lesson_defaults.get("lesson_1_reference")
        or "*Error: No first lesson found.*",
        "psalm_reference": lesson_defaults.get("psalm_reference")
        or "*Error: No psalm found.*",
        "lesson_2_reference": lesson_defaults.get("lesson_2_reference")
        or "*Error: No second lesson found.*",
        "gospel_reference": lesson_defaults.get("gospel_reference")
        or "*Error: No gospel found.*",
        "offertory_sentence": (
            offertory_sentence["text"]
            if offertory_sentence
            else "*Error: No offertory sentence found.*"
        ),
        "proper_preface": (
            proper_preface["text"]
            if proper_preface
            else "*Error: No proper preface found.*"
        ),
    }
    lesson_overrides = saved_data.get("lesson_overrides")
    if not isinstance(lesson_overrides, dict):
        lesson_overrides = {}
    override_map = {
        "lesson_1": "lesson_1_reference",
        "psalm": "psalm_reference",
        "lesson_2": "lesson_2_reference",
        "gospel": "gospel_reference",
    }
    for override_key, prop_key in override_map.items():
        custom_value = lesson_overrides.get(override_key)
        if custom_value:
            propers[prop_key] = custom_value
    service_title = (
        (observance.name or observance.alternative_name) if observance else ""
    )
    service_date_display = ""
    if saved_service and saved_service.get("service_date"):
        try:
            parsed_date = date.fromisoformat(saved_service["service_date"])
            service_date_display = (
                f"{parsed_date.strftime('%B')} {parsed_date.day}, {parsed_date.year}"
            )
        except ValueError:
            service_date_display = ""
    generated_at = datetime.now()
    generated_at_display = (
        f"{generated_at.strftime('%B')} {generated_at.day}, {generated_at.year} "
        f"at {generated_at.strftime('%I:%M %p').lstrip('0')}"
    )
    context = {
        "title": title,
        "rite": rite_name,
        "service_title": service_title,
        "service_date_display": service_date_display,
        "generated_at_display": generated_at_display,
        **propers,
    }

    rendered = []
    for item in ordinaries:
        if item.get("type") == "custom":
            rendered_text = item.get("text") or ""
            rendered_title = item.get("title") or ""
        else:
            rendered_text = render_template_text(item.get("text"), context)
            rendered_title = render_template_text(item.get("title"), context)
        rendered.append(
            {
                "title": rendered_title,
                "text": rendered_text,
                "type": item.get("type"),
            }
        )
    if include_metadata:
        return {
            "title": title,
            "rite": rite_name,
            "service_title": service_title,
            "service_date_display": service_date_display,
            "service_date": saved_service.get("service_date"),
            "generated_at_display": generated_at_display,
            "ordinaries": rendered,
        }
    return rendered
