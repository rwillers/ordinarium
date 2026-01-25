#!/usr/bin/env python3
import csv
import json
from pathlib import Path
from typing import Any


def get_db_path():
    from ordinarium import create_app

    app = create_app()
    return app.config["DATABASE"]


def normalize_json_value(value: Any):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return value
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return value
    return value


def table_columns(conn, table: str):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def sample_ids(conn, table: str, limit: int = 10):
    count = conn.execute(f"select count(*) from {table}").fetchone()[0]
    if count <= limit:
        rows = conn.execute(f"select id from {table} order by id").fetchall()
    else:
        rows = conn.execute(
            f"select id from {table} order by random() limit {limit}"
        ).fetchall()
    ids = [row[0] for row in rows]
    return sorted(ids)


TABLE_FIELDS = {
    "pages": ["id", "title", "content", "slug"],
    "services": [
        "id",
        "user_id",
        "title",
        "rite",
        "text_order",
        "text_disabled",
        "season",
        "service_date",
        "observance_handle",
        "lesson_overrides",
        "offertory_sentence_id",
    ],
    "users": [
        "id",
        "first_name",
        "last_name",
        "email",
        "password_hash",
    ],
    "texts": [
        "id",
        "type",
        "filter_type",
        "filter_content",
        "text",
        "title",
        "default_order",
        "detailed_title",
        "reading",
        "option_group",
        "optional",
        "book",
        "book_name",
        "reference_long",
        "reference_short",
        "note",
        "subcycles",
    ],
}

JSON_FALLBACK_PATHS = {
    "pages": {
        "title": "$.title",
        "content": "$.content",
        "slug": "$.slug",
    },
    "services": {
        "user_id": "$.user_id",
        "title": "$.title",
        "rite": "$.rite",
        "text_order": "$.text_order",
        "text_disabled": "$.text_disabled",
        "season": "$.season",
        "service_date": "$.service_date",
        "observance_handle": "$.observance_handle",
        "lesson_overrides": "$.lesson_overrides",
        "offertory_sentence_id": "$.offertory_sentence_id",
    },
    "users": {
        "first_name": "$.first_name",
        "last_name": "$.last_name",
        "email": "$.email",
        "password_hash": "$.password_hash",
    },
    "texts": {
        "type": "$.type",
        "filter_type": "$.filter.type",
        "filter_content": "$.filter.content",
        "text": "$.text",
        "title": "$.title",
        "default_order": "$.default_order",
        "detailed_title": "$.detailed_title",
        "reading": "$.reading",
        "option_group": "$.option_group",
        "optional": "$.optional",
        "book": "$.book",
        "book_name": "$.book_name",
        "reference_long": "$.reference_long",
        "reference_short": "$.reference_short",
        "note": "$.note",
        "subcycles": "$.subcycles",
    },
}

JSON_FIELDS = {
    "services": {"text_order", "text_disabled", "lesson_overrides"},
    "texts": {"subcycles"},
}


def build_select(table: str, columns: set[str], fields: list[str]):
    select_fields = []
    for field in fields:
        if field == "id":
            select_fields.append("id")
            continue
        if field in columns:
            select_fields.append(field)
            continue
        if "data" in columns:
            path = JSON_FALLBACK_PATHS[table].get(field)
            if path:
                select_fields.append(f"json_extract(data, '{path}') as {field}")
            else:
                select_fields.append(f"NULL as {field}")
        else:
            select_fields.append(f"NULL as {field}")
    return ", ".join(select_fields)


def snapshot_table(conn, table: str, output_dir: Path, limit: int = 10):
    ids = sample_ids(conn, table, limit=limit)
    fields = TABLE_FIELDS[table]
    columns = table_columns(conn, table)
    rows = []
    if ids:
        placeholders = ", ".join(["?"] * len(ids))
        select_sql = build_select(table, columns, fields)
        query = f"select {select_sql} from {table} where id in ({placeholders})"
        for row in conn.execute(query, ids).fetchall():
            row_dict = dict(row)
            for field in JSON_FIELDS.get(table, set()):
                row_dict[field] = normalize_json_value(row_dict.get(field))
            rows.append(row_dict)
        rows.sort(key=lambda item: item.get("id"))
    payload = {"table": table, "ids": ids, "rows": rows}

    json_path = output_dir / f"{table}.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    csv_path = output_dir / f"{table}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            row_out = dict(row)
            for field in JSON_FIELDS.get(table, set()):
                value = row_out.get(field)
                if isinstance(value, (dict, list)):
                    row_out[field] = json.dumps(value, sort_keys=True)
            writer.writerow(row_out)


def main():
    output_dir = Path("scripts/migration_snapshots")
    output_dir.mkdir(parents=True, exist_ok=True)

    import sqlite3

    conn = sqlite3.connect(get_db_path())
    try:
        conn.row_factory = sqlite3.Row
        for table in TABLE_FIELDS:
            snapshot_table(conn, table, output_dir)
    finally:
        conn.close()

    print(f"Snapshots written to {output_dir}")


if __name__ == "__main__":
    main()
