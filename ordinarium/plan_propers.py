import json


def _resolve_seasonal_text(db, text_type, season):
    row = None
    if season:
        row = db.execute(
            "select text from texts where type=? and filter_type=? and filter_content=? order by random() limit 1",
            (text_type, "season", season),
        ).fetchone()
    if not row:
        row = db.execute(
            "select text from texts where type=? and ((filter_type=? and filter_content=?) or (filter_type=? and filter_content=?)) order by random() limit 1",
            (text_type, "other", "At Any Time", "day", "The Lord’s Day"),
        ).fetchone()
    return row["text"] if row else None


def _resolve_collect_text(db, propers_list):
    if not propers_list:
        return None
    propers_json = json.dumps(propers_list)
    collect_text = db.execute(
        "select texts.text from texts join json_each(?) propers on texts.filter_content=propers.value where texts.type=? and texts.filter_type=? order by propers.key, texts.default_order limit 1",
        (propers_json, "collect", "proper"),
    ).fetchone()
    return collect_text["text"] if collect_text else None
