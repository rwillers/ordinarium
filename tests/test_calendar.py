from datetime import date

from ordinarium.liturgical_calendar import (
    _expand_date_rules,
    _parse_date_expression,
    _split_rule_condition,
    advent_start,
    easter_date,
    resolve_observance,
    resolve_observance_options,
    resolve_season,
)


def test_easter_date_known_year():
    assert easter_date(2024) == date(2024, 3, 31)


def test_advent_start_is_first_sunday_after_nov_27():
    assert advent_start(2024) == date(2024, 12, 1)


def test_resolve_season_known_dates():
    assert resolve_season(date(2024, 12, 25)) == "Christmastide"
    assert resolve_season(date(2024, 1, 5)) == "Christmastide"
    assert resolve_season(date(2024, 1, 6)) == "Epiphanytide"
    assert resolve_season(date(2024, 2, 14)) == "Lent"


def test_parse_date_expression_handles_easter_offset():
    assert _parse_date_expression("E+1", 2024) == date(2024, 4, 1)


def test_expand_date_rules_applies_conditions():
    rules = "12/25 (before 12/26), 12/25 (not on 12/25)"
    dates = _expand_date_rules(rules, 2024)
    assert dates == [date(2024, 12, 25)]


def test_split_rule_condition_parses_parts():
    base, condition = _split_rule_condition("12/25 (before 12/26)")
    assert base == "12/25"
    assert condition == "before 12/26"


def test_resolve_observance_options_sorts_by_priority_and_index(monkeypatch):
    def fake_holidays():
        return [
            {
                "index": 3,
                "handle": "C",
                "date": "12/01",
                "style": "Sunday",
                "priority": 2,
                "propers": ["C"],
                "name": "Third",
                "alternative_name": "",
            },
            {
                "index": 1,
                "handle": "A",
                "date": "12/01",
                "style": "Sunday",
                "priority": 1,
                "propers": ["A"],
                "name": "First",
                "alternative_name": "",
            },
            {
                "index": 2,
                "handle": "B",
                "date": "12/01",
                "style": "Sunday",
                "priority": 1,
                "propers": ["B"],
                "name": "Second",
                "alternative_name": "",
            },
        ]

    monkeypatch.setattr("ordinarium.liturgical_calendar._load_holidays", fake_holidays)
    options = resolve_observance_options(date(2024, 12, 1))
    handles = [option.handle for option in options]
    assert handles == ["A", "B", "C"]


def test_resolve_observance_prefers_handle_match(monkeypatch):
    def fake_holidays():
        return [
            {
                "index": 1,
                "handle": "A",
                "date": "12/01",
                "style": "Sunday",
                "priority": 1,
                "propers": ["A"],
                "name": "First",
                "alternative_name": "",
            },
            {
                "index": 2,
                "handle": "B",
                "date": "12/01",
                "style": "Sunday",
                "priority": 1,
                "propers": ["B"],
                "name": "Second",
                "alternative_name": "",
            },
        ]

    monkeypatch.setattr("ordinarium.liturgical_calendar._load_holidays", fake_holidays)
    observance = resolve_observance(date(2024, 12, 1), handle="B")
    assert observance.handle == "B"
