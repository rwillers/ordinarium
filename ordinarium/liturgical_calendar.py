import csv
import re
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional


def easter_date(year):
    # Anonymous Gregorian algorithm.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def advent_start(year):
    nov_27 = date(year, 11, 27)
    days_until_sunday = (6 - nov_27.weekday()) % 7
    return nov_27 + timedelta(days=days_until_sunday)


def resolve_season(service_date):
    if not service_date:
        return None

    easter = easter_date(service_date.year)
    ash_wednesday = easter - timedelta(days=46)
    palm_sunday = easter - timedelta(days=7)
    maundy_thursday = easter - timedelta(days=3)
    ascension = easter + timedelta(days=39)
    pentecost = easter + timedelta(days=49)
    trinity_sunday = easter + timedelta(days=56)

    advent = advent_start(service_date.year)
    christ_king = advent - timedelta(days=7)

    if service_date.month == 12 and service_date.day >= 25:
        return "Christmastide"
    if service_date.month == 1 and service_date.day <= 5:
        return "Christmastide"

    if service_date == christ_king:
        return "Christ the King"

    if advent <= service_date <= date(service_date.year, 12, 24):
        return "Advent"

    if date(service_date.year, 1, 6) <= service_date < ash_wednesday:
        return "Epiphanytide"

    if service_date == maundy_thursday:
        return "Maundy Thursday"

    if palm_sunday <= service_date < easter:
        return "Holy Week"

    if service_date == ascension:
        return "Ascension"

    if service_date == pentecost:
        return "Pentecost"

    if service_date == trinity_sunday:
        return "Trinity Sunday"

    if easter <= service_date < pentecost:
        return "Easter"

    if ash_wednesday <= service_date < palm_sunday:
        return "Lent"

    return "Ordinary Time"


DATA_DIR = Path(__file__).resolve().parents[1] / "Source Liturgies" / "ProperData"
HOLIDAYS_PATH = DATA_DIR / "Holidays.tsv"
FRAGMENTS_PATH = DATA_DIR / "Fragments.tsv"
SUBCYCLES_PATH = DATA_DIR / "Subcycles.tsv"

WEEKDAY_MAP = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}


@dataclass(frozen=True)
class Observance:
    handle: str
    name: str
    alternative_name: str
    propers: tuple[str, ...]
    style: str
    priority: int
    subcycle: Optional[str]


def resolve_sunday_title(service_date):
    observance = resolve_observance(service_date)
    if not observance:
        return None
    return observance.name or observance.alternative_name


def resolve_subcycle(service_date):
    if not service_date:
        return None
    subcycles = _load_subcycles()
    if not subcycles:
        return None
    epoch_year = subcycles[0]["epoch"]
    full_cycle = subcycles[0]["full_cycle"]
    lit_year = _resolve_liturgical_year(service_date)
    cycle_index = (lit_year - epoch_year) % full_cycle
    match = next(
        (cycle for cycle in subcycles if cycle["order"] == cycle_index),
        None,
    )
    return match["handle"] if match else None


def resolve_observance(service_date):
    if not service_date:
        return None
    holidays = _load_holidays()
    if not holidays:
        return None
    matches = []
    for holiday in holidays:
        for match_date in _expand_date_rules(holiday["date"], service_date.year):
            if match_date == service_date:
                matches.append(holiday)
                break
    if not matches:
        return None
    matches.sort(key=lambda item: (item["priority"], item["index"]))
    primary = matches[0]
    propers = list(primary["propers"])
    for fragment in _load_fragments():
        if fragment["behaviour"] != "Append":
            continue
        for match_date in _expand_date_rules(fragment["date"], service_date.year):
            if match_date == service_date:
                propers.extend(fragment["propers"])
                break
    return Observance(
        handle=primary["handle"],
        name=primary["name"],
        alternative_name=primary["alternative_name"],
        propers=tuple(_dedupe_list(propers)),
        style=primary["style"],
        priority=primary["priority"],
        subcycle=resolve_subcycle(service_date),
    )


def _resolve_liturgical_year(service_date):
    current_year = service_date.year
    if service_date >= advent_start(current_year):
        return current_year + 1
    return current_year


def _expand_date_rules(date_field, year):
    if not date_field or date_field == "_":
        return []
    dates = []
    for rule in [part.strip() for part in date_field.split(",") if part.strip()]:
        base_rule, condition = _split_rule_condition(rule)
        base_date = _parse_date_expression(base_rule, year)
        if not base_date:
            continue
        if condition:
            condition_lower = condition.lower()
            if condition_lower.startswith("before "):
                bound_date = _parse_date_expression(condition[7:].strip(), year)
                if not bound_date or base_date >= bound_date:
                    continue
            elif condition_lower.startswith("not on "):
                excluded_date = _parse_date_expression(condition[7:].strip(), year)
                if excluded_date and base_date == excluded_date:
                    continue
        dates.append(base_date)
    return dates


def _split_rule_condition(rule):
    match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", rule)
    if not match:
        return rule.strip(), ""
    return match.group(1).strip(), match.group(2).strip()


def _parse_date_expression(expression, year):
    if not expression:
        return None
    expression = expression.strip().replace(" ", "")
    if not expression or expression == "_":
        return None
    if expression.startswith("E"):
        easter = easter_date(year)
        if expression == "E":
            return easter
        match = re.match(r"^E([+-]\d+)$", expression)
        if match:
            return easter + timedelta(days=int(match.group(1)))
        return None
    if "→" in expression:
        base_expr, _, weekday = expression.partition("→")
        base_date = _parse_date_expression(base_expr, year)
        target_weekday = WEEKDAY_MAP.get(weekday.title())
        if base_date and target_weekday is not None:
            return _next_weekday(base_date, target_weekday)
        return None
    try:
        month_str, day_str = expression.split("/")
        return date(year, int(month_str), int(day_str))
    except ValueError:
        return None


def _next_weekday(start_date, target_weekday):
    days_until = (target_weekday - start_date.weekday()) % 7
    return start_date + timedelta(days=days_until)


def _dedupe_list(items):
    seen = set()
    deduped = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_propers(value):
    if not value or value == "_":
        return []
    return [item.strip() for item in value.split(",") if item.strip() and item != "_"]


def _normalize_header(header):
    header = header.strip()
    header = re.sub(r"\[.*\]$", "", header)
    return header.lstrip("$#!?*~")


def _read_tsv(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        rows = list(reader)
    if not rows:
        return []
    headers = [_normalize_header(header) for header in rows[0]]
    parsed = []
    for row in rows[1:]:
        if not row:
            continue
        item = {}
        for index, header in enumerate(headers):
            if index < len(row):
                item[header] = row[index].strip()
            else:
                item[header] = ""
        parsed.append(item)
    return parsed


@lru_cache(maxsize=1)
def _load_holidays():
    holidays = []
    for index, row in enumerate(_read_tsv(HOLIDAYS_PATH)):
        holidays.append(
            {
                "index": index,
                "handle": row.get("Handle", ""),
                "date": row.get("Date", ""),
                "style": row.get("Style", ""),
                "priority": _parse_int(row.get("Priority"), default=99),
                "propers": _parse_propers(row.get("Propers", "")),
                "name": row.get("Name", ""),
                "alternative_name": row.get("AlternativeName", ""),
            }
        )
    return holidays


@lru_cache(maxsize=1)
def _load_fragments():
    fragments = []
    for row in _read_tsv(FRAGMENTS_PATH):
        fragments.append(
            {
                "date": row.get("Date", ""),
                "behaviour": row.get("Behaviour", ""),
                "propers": _parse_propers(row.get("Propers", "")),
            }
        )
    return fragments


@lru_cache(maxsize=1)
def _load_subcycles():
    subcycles = []
    for row in _read_tsv(SUBCYCLES_PATH):
        subcycles.append(
            {
                "handle": row.get("Handle", ""),
                "epoch": _parse_int(row.get("Epoch"), default=0),
                "order": _parse_int(row.get("Order"), default=0),
                "full_cycle": _parse_int(row.get("FullCycle"), default=1),
            }
        )
    return subcycles
