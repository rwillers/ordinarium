import re
from datetime import date, timedelta

from .liturgical_constants import WEEKDAY_MAP
from .liturgical_data import _load_fragments
from .liturgical_dates import advent_start, easter_date


def _resolve_liturgical_year(service_date):
    current_year = service_date.year
    if service_date >= advent_start(current_year):
        return current_year + 1
    return current_year


def _matching_holidays(service_date):
    from . import liturgical_calendar

    holidays = liturgical_calendar._load_holidays()
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
    from . import liturgical_calendar

    for holiday in liturgical_calendar._load_holidays():
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
