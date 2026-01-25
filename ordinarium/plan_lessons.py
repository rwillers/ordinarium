import json
from datetime import date

from .db import get_db
from .liturgical_calendar import resolve_observance


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
        if reading_number in readings:
            continue
        readings[reading_number] = {
            "reference_short": row["reference_short"],
            "reference_long": row["reference_long"],
            "book": row["book"],
            "book_name": row["book_name"],
        }
    return readings


def _resolve_lesson_references(service_date, observance_handle):
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
    readings = _build_lesson_readings(propers_list, observance.subcycle)
    return {
        "lesson_1": _format_lesson_reference(readings.get(1)),
        "psalm": _format_lesson_reference(readings.get(2)),
        "lesson_2": _format_lesson_reference(readings.get(3)),
        "gospel": _format_lesson_reference(readings.get(5)),
    }
