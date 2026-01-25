from dataclasses import dataclass
from typing import Optional

from .liturgical_data import _load_subcycles
from .liturgical_rules import (
    _apply_fragments,
    _dedupe_list,
    _holiday_index,
    _matching_holidays,
    _resolve_liturgical_year,
)


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
