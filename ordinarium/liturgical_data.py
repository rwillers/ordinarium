from functools import lru_cache

from .db import get_database_gateway


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
    db = get_database_gateway()
    rows = db.fetch_all(
        "select id, handle, date_rule, style, priority, propers, name, alternative_name from holidays order by id"
    )
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
    db = get_database_gateway()
    rows = db.fetch_all(
        "select date_rule, behaviour, propers from fragments order by id"
    )
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
    db = get_database_gateway()
    rows = db.fetch_all(
        "select handle, epoch, order_value, full_cycle from subcycles order by id"
    )
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
