def _offertory_default_row(db, default_prefix):
    return db.fetch_one(
        "select id, text from texts where type=? and text like ? order by id limit 1",
        ("offertory_sentence", f"{default_prefix}%"),
    )


def _format_offertory_label(text, limit=110):
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if line.startswith("######"):
            continue
        label = line
        if len(label) > limit:
            label = label[: max(limit - 3, 0)].rstrip() + "..."
        return label
    return ""


def _load_offertory_sentences(db, default_prefix):
    rows = db.fetch_all(
        "select id, text from texts where type=? order by id",
        ("offertory_sentence",),
    )
    return [
        {
            "id": row["id"],
            "text": row["text"],
            "label": _format_offertory_label(row["text"]),
        }
        for row in rows
    ]


def _resolve_offertory_sentence(db, default_prefix, offertory_sentence_id=None):
    sentence_id = None
    if offertory_sentence_id:
        try:
            sentence_id = int(offertory_sentence_id)
        except (TypeError, ValueError):
            sentence_id = None
    if sentence_id:
        row = db.fetch_one(
            "select text from texts where id=? and type=? limit 1",
            (sentence_id, "offertory_sentence"),
        )
        if row:
            return row
    default_row = _offertory_default_row(db, default_prefix)
    if default_row:
        return default_row
    return db.fetch_one(
        "select text from texts where type=? order by id limit 1",
        ("offertory_sentence",),
    )
