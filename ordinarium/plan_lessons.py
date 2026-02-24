import json
from datetime import date

from .db import get_db
from .liturgical_calendar import resolve_observance

LESSON_READING_BY_KEY = {
    "lesson_1": 1,
    "psalm": 2,
    "lesson_2": 3,
    "gospel": 5,
}
LESSON_KEY_BY_READING = {value: key for key, value in LESSON_READING_BY_KEY.items()}


def _format_lesson_reference(lesson):
    if not lesson:
        return None
    reference_short = lesson.get("reference_short")
    if reference_short and reference_short.strip() == "_":
        reference_short = None
    reference = reference_short or lesson.get("reference_long")
    if not reference:
        return None
    book_name = lesson.get("book_name") or lesson.get("book")
    if not book_name:
        return reference
    return f"{book_name} ({reference})"


def _build_lesson_readings(propers_list, subcycle):
    options_by_reading = _build_lesson_reading_options(propers_list, subcycle)
    return {
        reading: options[0]
        for reading, options in options_by_reading.items()
        if options
    }


def _build_lesson_reading_options(propers_list, subcycle):
    if not propers_list:
        return {}
    db = get_db()
    propers_json = json.dumps(propers_list)
    lessons = db.execute(
        """
        select
          reading,
          optional,
          subcycles,
          default_order,
          reference_short,
          reference_long,
          book,
          book_name
        from texts
        join json_each(?) propers on texts.filter_content=propers.value
        where texts.type=? and texts.filter_type=?
        order by propers.key, texts.default_order
        """,
        (propers_json, "lesson", "proper"),
    ).fetchall()
    readings = {}
    signatures = {}
    if not lessons:
        return readings
    for row in lessons:
        if row["optional"]:
            continue
        lesson_subcycles = []
        if row["subcycles"]:
            try:
                parsed_subcycles = json.loads(row["subcycles"])
                if isinstance(parsed_subcycles, list):
                    lesson_subcycles = parsed_subcycles
            except json.JSONDecodeError:
                lesson_subcycles = []
        if lesson_subcycles and subcycle and subcycle not in lesson_subcycles:
            continue
        reading_number = row["reading"]
        if reading_number not in LESSON_KEY_BY_READING:
            continue
        signature = (
            row["book_name"] or row["book"],
            row["reference_short"],
            row["reference_long"],
        )
        seen = signatures.setdefault(reading_number, set())
        if signature in seen:
            continue
        seen.add(signature)
        readings.setdefault(reading_number, []).append(
            {
                "reference_short": row["reference_short"],
                "reference_long": row["reference_long"],
                "book": row["book"],
                "book_name": row["book_name"],
                "default_order": row["default_order"] or 0,
            }
        )
    return readings


def _resolve_lesson_reference_alternates(service_date, observance_handle):
    if not service_date:
        return {}
    try:
        parsed_date = date.fromisoformat(service_date)
    except ValueError:
        return {}
    observance = resolve_observance(parsed_date, observance_handle)
    if not observance:
        return {}
    propers_list = list(observance.propers)
    options_by_reading = _build_lesson_reading_options(
        propers_list, observance.subcycle
    )
    alternates = {}
    for reading, options in options_by_reading.items():
        lesson_key = LESSON_KEY_BY_READING.get(reading)
        if not lesson_key or len(options) < 2:
            continue
        formatted = []
        seen = set()
        for option in options[1:]:
            reference = _format_lesson_reference(option)
            if not reference or reference in seen:
                continue
            seen.add(reference)
            formatted.append(reference)
        if formatted:
            alternates[lesson_key] = formatted
    return alternates


def _resolve_lesson_reference_options(service_date, observance_handle):
    if not service_date:
        return {}
    try:
        parsed_date = date.fromisoformat(service_date)
    except ValueError:
        return {}
    observance = resolve_observance(parsed_date, observance_handle)
    if not observance:
        return {}
    propers_list = list(observance.propers)
    options_by_reading = _build_lesson_reading_options(
        propers_list, observance.subcycle
    )
    output = {}
    for reading, options in options_by_reading.items():
        lesson_key = LESSON_KEY_BY_READING.get(reading)
        if not lesson_key:
            continue
        formatted = []
        seen = set()
        for option in options:
            reference = _format_lesson_reference(option)
            if not reference or reference in seen:
                continue
            seen.add(reference)
            formatted.append(reference)
        if formatted:
            output[lesson_key] = formatted
    return output


def _resolve_lesson_references(service_date, observance_handle):
    options = _resolve_lesson_reference_options(service_date, observance_handle)
    return {
        "lesson_1": (options.get("lesson_1") or [None])[0],
        "psalm": (options.get("psalm") or [None])[0],
        "lesson_2": (options.get("lesson_2") or [None])[0],
        "gospel": (options.get("gospel") or [None])[0],
    }
