import re
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from typing import Optional

from .db import get_db


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


def resolve_observance(service_date, handle=None):
    if not service_date:
        return None
    options = resolve_observance_options(service_date)
    if not options:
        return None
    if handle:
        for option in options:
            if option.handle == handle:
                return option
    return options[0]


def resolve_observance_options(service_date):
    if not service_date:
        return []
    matches = _matching_holidays(service_date)
    if not matches:
        return []
    options = []
    for holiday in matches:
        propers = list(holiday["propers"])
        if holiday["style"].lower() == "sunday":
            propers = _apply_fragments(propers, service_date)
        options.append(
            Observance(
                handle=holiday["handle"],
                name=holiday["name"],
                alternative_name=holiday["alternative_name"],
                propers=tuple(_dedupe_list(propers)),
                style=holiday["style"],
                priority=holiday["priority"],
                subcycle=resolve_subcycle(service_date),
            )
        )
    options.sort(key=lambda item: (item.priority, _holiday_index(item.handle)))
    return options


def _resolve_liturgical_year(service_date):
    current_year = service_date.year
    if service_date >= advent_start(current_year):
        return current_year + 1
    return current_year


def _matching_holidays(service_date):
    holidays = _load_holidays()
    if not holidays:
        return []
    matches = []
    for holiday in holidays:
        for match_date in _expand_date_rules(holiday["date"], service_date.year):
            if match_date == service_date:
                matches.append(holiday)
                break
    matches.sort(key=lambda item: (item["priority"], item["index"]))
    return matches


def _holiday_index(handle):
    for holiday in _load_holidays():
        if holiday["handle"] == handle:
            return holiday["index"]
    return 0


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


def _apply_fragments(propers, service_date):
    for fragment in _load_fragments():
        if fragment["behaviour"] != "Append":
            continue
        for match_date in _expand_date_rules(fragment["date"], service_date.year):
            if match_date == service_date:
                propers.extend(fragment["propers"])
                break
    return propers


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


@lru_cache(maxsize=1)
def _load_holidays():
    holidays = []
    db = get_db()
    rows = db.execute(
        "select id, handle, date_rule, style, priority, propers, name, alternative_name from holidays order by id"
    ).fetchall()
    for row in rows:
        holidays.append(
            {
                "index": row["id"] - 1,
                "handle": row["handle"] or "",
                "date": row["date_rule"] or "",
                "style": row["style"] or "",
                "priority": _parse_int(row["priority"], default=99),
                "propers": _parse_propers(row["propers"]),
                "name": row["name"] or "",
                "alternative_name": row["alternative_name"] or "",
            }
        )
    return holidays


@lru_cache(maxsize=1)
def _load_fragments():
    fragments = []
    db = get_db()
    rows = db.execute(
        "select date_rule, behaviour, propers from fragments order by id"
    ).fetchall()
    for row in rows:
        fragments.append(
            {
                "date": row["date_rule"] or "",
                "behaviour": row["behaviour"] or "",
                "propers": _parse_propers(row["propers"]),
            }
        )
    return fragments


@lru_cache(maxsize=1)
def _load_subcycles():
    subcycles = []
    db = get_db()
    rows = db.execute(
        "select handle, epoch, order_value, full_cycle from subcycles order by id"
    ).fetchall()
    for row in rows:
        subcycles.append(
            {
                "handle": row["handle"] or "",
                "epoch": _parse_int(row["epoch"], default=0),
                "order": _parse_int(row["order_value"], default=0),
                "full_cycle": _parse_int(row["full_cycle"], default=1),
            }
        )
    return subcycles
