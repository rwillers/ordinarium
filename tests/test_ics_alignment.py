import os
import random
import re
from datetime import date, timedelta
from urllib.request import urlopen

import pytest

from ordinarium.liturgical_calendar import (
    resolve_observance_options,
    resolve_season,
)

ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "ma7m909q4huvqedci3fbl1u6rg%40group.calendar.google.com/"
    "public/basic.ics"
)

ORDINAL_WORDS = {
    1: "first",
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
    9: "ninth",
    10: "tenth",
    11: "eleventh",
    12: "twelfth",
    13: "thirteenth",
    14: "fourteenth",
    15: "fifteenth",
    16: "sixteenth",
    17: "seventeenth",
    18: "eighteenth",
    19: "nineteenth",
    20: "twentieth",
    21: "twenty first",
    22: "twenty second",
    23: "twenty third",
    24: "twenty fourth",
    25: "twenty fifth",
    26: "twenty sixth",
    27: "twenty seventh",
}


def _fetch_ics(url):
    with urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


def _unfold_lines(text):
    lines = text.splitlines()
    unfolded = []
    for line in lines:
        if line.startswith(" "):
            if unfolded:
                unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _parse_events(text):
    events = []
    current = None
    for line in _unfold_lines(text):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            if current:
                events.append(current)
            current = None
        elif current is not None:
            if ":" in line:
                key, value = line.split(":", 1)
                current[key] = _unescape_ics_text(value)
    return events


def _unescape_ics_text(value):
    return (
        value.replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _event_date(event):
    dtstart = next((value for key, value in event.items() if key.startswith("DTSTART")), None)
    if not dtstart:
        return None
    if "T" in dtstart:
        dtstart = dtstart.split("T", 1)[0]
    if len(dtstart) != 8 or not dtstart.isdigit():
        return None
    return date(int(dtstart[0:4]), int(dtstart[4:6]), int(dtstart[6:8]))


def _normalize_title(title):
    title = re.sub(r"\([^)]*\)", "", title)
    title = title.lower()
    title = title.replace("'", "")
    title = title.replace("’", "")
    title = title.replace("-", " ")
    title = re.sub(r"[^a-z0-9\\s]", " ", title)
    title = re.sub(r"\\s+", " ", title).strip()
    stop_words = {"the", "of", "in", "after", "sunday", "day", "optional", "or", "year", "and"}
    tokens = [
        token
        for token in title.split()
        if token not in stop_words and not token.isdigit()
    ]
    return " ".join(tokens)


def _summary_to_observance(summary):
    summary = summary.strip()
    lower = summary.lower()
    if "sunday after ascension" in lower:
        return "The Seventh Sunday of Easter"
    if lower == "pentecost":
        return "The Day of Pentecost"
    match = re.search(r"pentecost\s*(\d+)", lower)
    if match:
        number = int(match.group(1))
        ordinal = ORDINAL_WORDS.get(number)
        if ordinal:
            return f"The {ordinal} Sunday After Pentecost"
    return summary


def _infer_season_from_summary(summary):
    lower = summary.lower()
    if "advent" in lower:
        return "Advent"
    if "christmas" in lower:
        return "Christmastide"
    if "epiphany" in lower:
        return "Epiphanytide"
    if "lent" in lower:
        return "Lent"
    if "palm sunday" in lower or "holy week" in lower:
        return "Holy Week"
    if lower.strip() == "pentecost":
        return "Pentecost"
    if "trinity sunday" in lower:
        return "Trinity Sunday"
    if "christ the king" in lower or "last sunday after pentecost" in lower:
        return "Christ the King"
    if "after pentecost" in lower or lower.startswith("pentecost "):
        return "Ordinary Time"
    if "ascension" in lower:
        if lower.strip() == "ascension":
            return "Ascension"
        return "Easter"
    if "easter" in lower:
        return "Easter"
    return None


def _add_years(start, years):
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        return start.replace(month=2, day=28, year=start.year + years)


def _sunday_dates(start, end):
    offset = (6 - start.weekday()) % 7
    current = start + timedelta(days=offset)
    while current <= end:
        yield current
        current += timedelta(days=7)


def test_sunday_sample_matches_ics_observance_and_season():
    if os.getenv("SKIP_ICS_TESTS"):
        pytest.skip("Skipping ICS alignment test via SKIP_ICS_TESTS.")
    ics_text = _fetch_ics(ICS_URL)
    events = _parse_events(ics_text)
    events_by_date = {}
    for event in events:
        event_date = _event_date(event)
        if not event_date:
            continue
        events_by_date.setdefault(event_date, []).append(event)

    today = date.today()
    end_date = _add_years(today, 3)
    candidates = list(_sunday_dates(today, end_date))
    rng = random.Random(42)
    rng.shuffle(candidates)

    checked = 0
    for candidate in candidates:
        if checked >= 10:
            break
        events_for_date = events_by_date.get(candidate, [])
        if not events_for_date:
            continue
        summary = None
        for event in events_for_date:
            value = event.get("SUMMARY", "")
            lower = value.lower()
            if "sunday" in lower or lower.startswith("pentecost") or lower == "pentecost":
                summary = value
                break
        if not summary:
            continue
        inferred_season = _infer_season_from_summary(summary)
        if not inferred_season:
            continue
        options = resolve_observance_options(candidate)
        if not options:
            continue
        normalized_options = {
            _normalize_title(option.name or option.alternative_name or "")
            for option in options
        }
        expected = _summary_to_observance(summary)
        assert _normalize_title(expected) in normalized_options, (
            f"Observance mismatch for {candidate}: "
            f"ics='{summary}' local={[option.name or option.alternative_name for option in options]}"
        )
        assert resolve_season(candidate) == inferred_season, (
            f"Season mismatch for {candidate}: "
            f"ics='{summary}' local='{resolve_season(candidate)}'"
        )
        checked += 1

    assert checked == 10, f"Only validated {checked} Sundays from ICS data."
