from .db import get_db
from .service_defaults import DEFAULT_RITE


def load_rite_options():
    db = get_db()
    rows = db.execute(
        "select distinct filter_content from texts where type=? and filter_type=? order by filter_content",
        ("ordinarium", "rite"),
    ).fetchall()
    options = [row["filter_content"] for row in rows if row["filter_content"]]
    if DEFAULT_RITE not in options:
        options.insert(0, DEFAULT_RITE)
    return options
