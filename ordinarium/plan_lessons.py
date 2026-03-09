import json
import re
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

BIBLIA_TRANSLATION_CODES = {
    "ESV": "esv",
    "NRSV": "nrsv",
    "NIV": "niv2011",
}

_LESSON_BIBLIA_BOOK_CODES = {
    "acts": "Acts",
    "amos": "Amos",
    "col": "Col",
    "colossians": "Col",
    "dan": "Dan",
    "daniel": "Dan",
    "deut": "Deut",
    "deuteronomy": "Deut",
    "eccl": "Eccl",
    "ecclesiastes": "Eccl",
    "eph": "Eph",
    "ephesians": "Eph",
    "exod": "Exod",
    "exodus": "Exod",
    "ezek": "Ezek",
    "ezekiel": "Ezek",
    "gal": "Gal",
    "galatians": "Gal",
    "gen": "Gen",
    "genesis": "Gen",
    "hab": "Hab",
    "habakkuk": "Hab",
    "heb": "Heb",
    "hebrews": "Heb",
    "hos": "Hos",
    "hosea": "Hos",
    "1 cor": "1Cor",
    "1 corinthians": "1Cor",
    "i corinthians": "1Cor",
    "1 john": "1John",
    "i john": "1John",
    "1 kgs": "1Kgs",
    "1 kings": "1Kgs",
    "i kings": "1Kgs",
    "1 pet": "1Pet",
    "1 peter": "1Pet",
    "i peter": "1Pet",
    "1 sam": "1Sam",
    "1 samuel": "1Sam",
    "i samuel": "1Sam",
    "1 thess": "1Thess",
    "1 thessalonians": "1Thess",
    "i thessalonians": "1Thess",
    "1 tim": "1Tim",
    "1 timothy": "1Tim",
    "i timothy": "1Tim",
    "2 chr": "2Chr",
    "2 chronicles": "2Chr",
    "ii chronicles": "2Chr",
    "2 cor": "2Cor",
    "2 corinthians": "2Cor",
    "ii corinthians": "2Cor",
    "2 kgs": "2Kgs",
    "2 kings": "2Kgs",
    "ii kings": "2Kgs",
    "2 pet": "2Pet",
    "2 peter": "2Pet",
    "ii peter": "2Pet",
    "2 sam": "2Sam",
    "2 samuel": "2Sam",
    "ii samuel": "2Sam",
    "2 thess": "2Thess",
    "2 thessalonians": "2Thess",
    "ii thessalonians": "2Thess",
    "2 tim": "2Tim",
    "2 timothy": "2Tim",
    "ii timothy": "2Tim",
    "isa": "Isa",
    "isaiah": "Isa",
    "jas": "Jas",
    "james": "Jas",
    "jer": "Jer",
    "jeremiah": "Jer",
    "job": "Job",
    "joel": "Joel",
    "john": "John",
    "jonah": "Jonah",
    "josh": "Josh",
    "joshua": "Josh",
    "judg": "Judg",
    "judges": "Judg",
    "jdt": "Jdt",
    "judith": "Jdt",
    "lam": "Lam",
    "lamentations": "Lam",
    "lev": "Lev",
    "leviticus": "Lev",
    "luke": "Luke",
    "mal": "Mal",
    "malachi": "Mal",
    "mark": "Mark",
    "matt": "Matt",
    "matthew": "Matt",
    "mic": "Mic",
    "micah": "Mic",
    "neh": "Neh",
    "nehemiah": "Neh",
    "num": "Num",
    "numbers": "Num",
    "phlm": "Phlm",
    "philemon": "Phlm",
    "phil": "Phil",
    "philippians": "Phil",
    "prov": "Prov",
    "proverbs": "Prov",
    "ps": "Ps",
    "psalm": "Ps",
    "rev": "Rev",
    "revelation": "Rev",
    "rom": "Rom",
    "romans": "Rom",
    "ruth": "Ruth",
    "sir": "Sir",
    "sirach": "Sir",
    "titus": "Titus",
    "wis": "Wis",
    "wisdom": "Wis",
    "zech": "Zech",
    "zechariah": "Zech",
    "zeph": "Zeph",
    "zephaniah": "Zeph",
}

_DISPLAY_REFERENCE_PATTERN = re.compile(
    r"^\s*(?P<book>.+?)\s*\((?P<reference>[^()]+)\)\s*$"
)
_INLINE_REFERENCE_PATTERN = re.compile(
    r"^\s*(?P<book>(?:[1-3]|I{1,3})?\s*[A-Za-z][A-Za-z .]+?)\s+"
    r"(?P<reference>\d[\dA-Za-z:,\-– ]*)\s*$"
)
_REFERENCE_ALLOWED_PATTERN = re.compile(r"^[0-9A-Za-z:,\-– ]+$")


def _format_lesson_reference(lesson):
    if not lesson:
        return None
    reference = _lesson_reference_value(lesson)
    if not reference:
        return None
    book_name = lesson.get("book_name") or lesson.get("book")
    if not book_name:
        return reference
    return f"{book_name} ({reference})"


def format_lesson_reference_with_biblia(reference_text, translation, lesson=None):
    display_text = (reference_text or "").strip()
    if not display_text:
        return None
    if display_text.startswith("*Error:") or "](" in display_text:
        return display_text

    translation_code = BIBLIA_TRANSLATION_CODES.get((translation or "").strip().upper())
    if not translation_code:
        return display_text

    book_code = None
    reference_path = None
    if isinstance(lesson, dict):
        book_code = _lookup_lesson_biblia_book_code(
            lesson.get("book"),
            lesson.get("book_name"),
        )
        reference_path = _normalize_biblia_reference(_lesson_reference_value(lesson))

    if not book_code or not reference_path:
        parsed_book, parsed_reference = _parse_lesson_reference_text(display_text)
        book_code = _lookup_lesson_biblia_book_code(parsed_book)
        reference_path = _normalize_biblia_reference(parsed_reference)

    if not book_code or not reference_path:
        return display_text

    escaped_text = _escape_markdown_link_text(display_text)
    return (
        f"[{escaped_text}]"
        f"(https://biblia.com/books/{translation_code}/{book_code}{reference_path})"
    )


def _lesson_reference_value(lesson):
    if not lesson:
        return None
    reference_short = lesson.get("reference_short")
    if reference_short and reference_short.strip() == "_":
        reference_short = None
    reference = reference_short or lesson.get("reference_long")
    if reference is None:
        return None
    normalized = str(reference).strip()
    return normalized or None


def _lookup_lesson_biblia_book_code(*candidates):
    for candidate in candidates:
        if candidate is None:
            continue
        normalized = " ".join(str(candidate).strip().lower().split())
        if not normalized:
            continue
        code = _LESSON_BIBLIA_BOOK_CODES.get(normalized)
        if code:
            return code
    return None


def _normalize_biblia_reference(reference):
    if reference is None:
        return None
    normalized = str(reference).strip()
    if not normalized:
        return None
    primary_segment = normalized.split(",", 1)[0].strip()
    if not primary_segment or not _REFERENCE_ALLOWED_PATTERN.fullmatch(primary_segment):
        return None
    return primary_segment.replace("–", "-").replace(" ", "").replace(":", ".")


def _parse_lesson_reference_text(display_text):
    match = _DISPLAY_REFERENCE_PATTERN.match(display_text or "")
    if match:
        return match.group("book").strip(), match.group("reference").strip()
    match = _INLINE_REFERENCE_PATTERN.match(display_text or "")
    if match:
        return match.group("book").strip(), match.group("reference").strip()
    return None, None


def _escape_markdown_link_text(value):
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


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
