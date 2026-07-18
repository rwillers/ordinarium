import json
import re
from datetime import date, datetime

from flask import current_app, render_template, request

from .db import get_database_gateway
from .error_pages import render_error
from .liturgical_calendar import resolve_observance
from .service_option_rendering import (
    apply_greeting_response_preference,
    apply_service_option_overrides,
)
from .service_defaults import OFFERTORY_DEFAULT_PREFIX
from .service_planning import (
    build_plan_items,
    parse_plan_tokens,
    _build_lesson_readings,
    _format_lesson_reference,
    format_lesson_reference_with_biblia,
    _resolve_offertory_sentence,
    _resolve_proper_override,
)
from .user_settings import (
    resolve_default_bible_translation,
    resolve_greeting_response_form,
)

RAT_RITE = "Renewed Ancient Text"
AST_RITE = "Anglican Standard Text"
_CROSS_RITE_TITLES = (
    "The Prayers of the People",
    "The Post Communion Prayer",
    "The Confession and Absolution of Sin",
    "The Ministration of Communion",
)
_OPTION_VARIANT_HANDLES = (
    "creed.apostles",
    "creed.athanasian",
    "confession.morning_prayer",
)


def _other_rite_name(rite_name):
    if rite_name == RAT_RITE:
        return AST_RITE
    if rite_name == AST_RITE:
        return RAT_RITE
    return None


def _load_cross_rite_swap_texts(db, rite_name):
    other_rite = _other_rite_name(rite_name)
    if not other_rite:
        return {}
    placeholders = ",".join("?" for _ in _CROSS_RITE_TITLES)
    rows = db.fetch_all(
        f"""
        select title, text
        from texts
        where type=?
          and filter_type=?
          and filter_content=?
          and title in ({placeholders})
        """,
        ("ordinarium", "rite", other_rite, *_CROSS_RITE_TITLES),
    )
    return {row["title"]: row["text"] for row in rows}


def _load_option_variant_texts(db):
    placeholders = ",".join("?" for _ in _OPTION_VARIANT_HANDLES)
    rows = db.fetch_all(
        f"""
        select filter_content, title, text
        from texts
        where type=?
          and filter_type=?
          and filter_content in ({placeholders})
        """,
        ("ordinarium", "handle", *_OPTION_VARIANT_HANDLES),
    )
    return {
        row["filter_content"]: {"title": row["title"], "text": row["text"]}
        for row in rows
    }


def _apply_service_option_text_swaps(
    ordinaries,
    rite_name,
    service_option_values,
    swap_texts,
    option_variant_texts,
):
    if not isinstance(ordinaries, list) or not ordinaries:
        return ordinaries
    if not isinstance(service_option_values, dict):
        return ordinaries

    prayers_form = service_option_values.get("prayers.form")
    target_prayers_rite = None
    if prayers_form == "rat":
        target_prayers_rite = RAT_RITE
    elif prayers_form == "ast":
        target_prayers_rite = AST_RITE
    swap_prayers = bool(target_prayers_rite and target_prayers_rite != rite_name)
    swap_post_communion = (
        service_option_values.get("post_communion.form") == "other_rite"
    )
    swap_confession = service_option_values.get("confession.form") == "other_rite"
    swap_distribution_source = (
        service_option_values.get("communion.distribution.source_rite") == "other_rite"
    )
    creed_form = service_option_values.get("creed.form")
    confession_form = service_option_values.get("confession.form")

    if not any(
        (
            swap_prayers,
            swap_post_communion,
            swap_confession,
            swap_distribution_source,
            creed_form in {"apostles", "athanasian"},
            confession_form == "morning_prayer",
        )
    ):
        return ordinaries

    updated = []
    for item in ordinaries:
        output = dict(item)
        if output.get("type") == "custom":
            updated.append(output)
            continue
        title = output.get("title") or ""
        if swap_prayers and title == "The Prayers of the People":
            swapped = swap_texts.get("The Prayers of the People")
            if swapped:
                output["text"] = swapped
        elif swap_post_communion and title == "The Post Communion Prayer":
            swapped = swap_texts.get("The Post Communion Prayer")
            if swapped:
                output["text"] = swapped
        elif title == "The Nicene Creed":
            variant_handle = {
                "apostles": "creed.apostles",
                "athanasian": "creed.athanasian",
            }.get(creed_form)
            variant = (
                option_variant_texts.get(variant_handle) if variant_handle else None
            )
            if variant:
                output["title"] = variant["title"]
                output["detailed_title"] = variant["title"]
                output["text"] = variant["text"]
        elif title == "The Confession and Absolution of Sin":
            if confession_form == "morning_prayer":
                variant = option_variant_texts.get("confession.morning_prayer")
                if variant:
                    output["text"] = variant["text"]
            elif swap_confession:
                swapped = swap_texts.get("The Confession and Absolution of Sin")
                if swapped:
                    output["text"] = swapped
        elif title == "The Ministration of Communion" and swap_distribution_source:
            swapped = swap_texts.get("The Ministration of Communion")
            if swapped:
                output["text"] = _swap_communion_distribution_formulas(
                    output.get("text") or "",
                    swapped,
                )
        updated.append(output)
    return updated


def _swap_communion_distribution_formulas(text, other_rite_text):
    pattern = re.compile(
        r"(?s)(.*\*The Bread and Cup are given to the communicants with these words\*\n\n)"
        r"(The Body of our Lord Jesus Christ, \[.*?\]\n\n"
        r"The Blood of our Lord Jesus Christ, \[.*?\])"
        r"(\n\n\*During the ministration of Communion,.*)"
    )
    current_match = pattern.fullmatch(text or "")
    other_match = pattern.fullmatch(other_rite_text or "")
    if not current_match or not other_match:
        return text
    return f"{current_match.group(1)}{other_match.group(2)}{current_match.group(3)}"


def render_text_page(service_id, saved_service, saved_data, user_id=None):
    if not saved_service:
        return render_error("Service ID required to generate text.", 400)
    if not saved_service["rite"]:
        return render_error("Service rite is required to generate text.", 400)
    rendered_service = dict(saved_service)
    season = request.args.get("season", "").strip()
    if rendered_service.get("season"):
        season = rendered_service["season"]
    elif season:
        rendered_service["season"] = season

    context = build_rendered_ordinaries(
        service_id,
        rendered_service,
        saved_data,
        user_id=user_id,
        include_metadata=True,
    )
    if not context:
        return render_error("Content not found.", 404)
    return render_template(
        "text.html",
        service_id=service_id,
        allow_export=bool(user_id),
        **context,
    )


def build_rendered_ordinaries(
    service_id,
    saved_service,
    saved_data,
    user_id=None,
    include_metadata=False,
    link_lesson_references=True,
):
    if not saved_service:
        return None
    if not isinstance(saved_service, dict):
        saved_service = dict(saved_service)
    if not saved_service.get("rite"):
        return None
    db = get_database_gateway()
    text_cache = {}

    def fetch_text(text_type, filter_type, filter_content, random_choice=False):
        key = (text_type, filter_type, filter_content)
        if key in text_cache:
            return text_cache[key]
        order_clause = "order by random()" if random_choice else ""
        row = db.fetch_one(
            f"select text from texts where type=? and filter_type=? and filter_content=? {order_clause} limit 1",
            (text_type, filter_type, filter_content),
        )
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
            "token": item.get("token"),
            "title": item.get("title"),
            "detailed_title": item.get("detailed_title"),
            "text": item.get("text"),
            "type": item.get("type"),
        }
        for item in plan_items
        if not item.get("disabled")
    ]
    if not ordinaries:
        return None

    season = saved_service.get("season") or ""
    cross_rite_swap_texts = _load_cross_rite_swap_texts(db, rite_name)
    option_variant_texts = _load_option_variant_texts(db)
    ordinaries = _apply_service_option_text_swaps(
        ordinaries,
        rite_name,
        saved_data.get("service_option_values"),
        cross_rite_swap_texts,
        option_variant_texts,
    )
    ordinaries = apply_service_option_overrides(
        ordinaries, saved_data.get("service_option_values"), season=season
    )
    ordinaries = apply_greeting_response_preference(
        ordinaries,
        resolve_greeting_response_form(
            (saved_data or {}).get("greeting_response_form")
        ),
    )

    acclamation = None
    if season:
        acclamation = fetch_text("acclamation", "season", season, random_choice=True)
    if not acclamation:
        acclamation = db.fetch_one(
            "select text from texts where type=? and ((filter_type=? and filter_content=?) or (filter_type=? and filter_content=?)) order by random() limit 1",
            ("acclamation", "other", "At Any Time", "day", "The Lord’s Day"),
        )
    offertory_sentence = _resolve_offertory_sentence(
        db, OFFERTORY_DEFAULT_PREFIX, saved_data.get("offertory_sentence_id")
    )
    proper_preface = None
    if season:
        proper_preface = fetch_text(
            "proper_preface", "season", season, random_choice=True
        )
    if not proper_preface:
        proper_preface = db.fetch_one(
            "select text from texts where type=? and ((filter_type=? and filter_content=?) or (filter_type=? and filter_content=?)) order by random() limit 1",
            ("proper_preface", "other", "At Any Time", "day", "The Lord’s Day"),
        )
    decalogue_text = fetch_text("law_form", "rite", rite_name)

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
        collect_text = db.fetch_one(
            "select texts.text from texts join json_each(?) propers on texts.filter_content=propers.value where texts.type=? and texts.filter_type=? order by propers.key, texts.default_order limit 1",
            (propers_json, "collect", "proper"),
        )
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
    bible_translation = resolve_default_bible_translation(
        (saved_data or {}).get("default_bible_translation")
    )
    lesson_defaults = {
        "lesson_1_reference": _render_lesson_reference(
            _format_lesson_reference(readings.get(1)),
            bible_translation,
            lesson=readings.get(1),
            link_lesson_references=link_lesson_references,
        ),
        "psalm_reference": _render_lesson_reference(
            _format_lesson_reference(readings.get(2)),
            bible_translation,
            lesson=readings.get(2),
            link_lesson_references=link_lesson_references,
        ),
        "lesson_2_reference": _render_lesson_reference(
            _format_lesson_reference(readings.get(3)),
            bible_translation,
            lesson=readings.get(3),
            link_lesson_references=link_lesson_references,
        ),
        "gospel_reference": _render_lesson_reference(
            _format_lesson_reference(readings.get(5)),
            bible_translation,
            lesson=readings.get(5),
            link_lesson_references=link_lesson_references,
        ),
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
        "decalogue_text": (
            decalogue_text["text"]
            if decalogue_text
            else "*Error: No Decalogue text found.*"
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
            propers[prop_key] = _render_lesson_reference(
                custom_value,
                bible_translation,
                link_lesson_references=link_lesson_references,
            )
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
                "token": item.get("token"),
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
            "service_option_values": saved_data.get("service_option_values") or {},
            "ordinaries": rendered,
        }
    return rendered


def _render_lesson_reference(
    reference_text,
    bible_translation,
    lesson=None,
    link_lesson_references=True,
):
    if not reference_text:
        return None
    if not link_lesson_references:
        return reference_text
    return format_lesson_reference_with_biblia(
        reference_text,
        bible_translation,
        lesson=lesson,
    )
