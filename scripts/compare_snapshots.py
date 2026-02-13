#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from typing import Any


def get_db_path():
    from ordinarium import create_app

    app = create_app()
    return app.config["DATABASE"]


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
        "proper_overrides",
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

JSON_FIELDS = {
    "services": {
        "text_order",
        "text_disabled",
        "lesson_overrides",
        "proper_overrides",
    },
    "texts": {"subcycles"},
}


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


def normalize_row(table: str, row: dict):
    normalized = dict(row)
    for field in JSON_FIELDS.get(table, set()):
        normalized[field] = normalize_json_value(normalized.get(field))
    return normalized


def load_snapshots(snapshot_dir: Path):
    snapshots = {}
    for table in TABLE_FIELDS:
        path = snapshot_dir / f"{table}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = [normalize_row(table, row) for row in payload.get("rows", [])]
        snapshots[table] = {
            "ids": payload.get("ids", []),
            "rows": rows,
        }
    return snapshots


def fetch_rows(conn, table: str, ids: list[int]):
    if not ids:
        return []
    placeholders = ", ".join(["?"] * len(ids))
    fields = TABLE_FIELDS[table]
    query = f"select {', '.join(fields)} from {table} where id in ({placeholders})"
    rows = [dict(row) for row in conn.execute(query, ids).fetchall()]
    rows.sort(key=lambda item: item.get("id"))
    return [normalize_row(table, row) for row in rows]


def main():
    snapshot_dir = Path("scripts/migration_snapshots")
    if len(sys.argv) > 1:
        snapshot_dir = Path(sys.argv[1])

    snapshots = load_snapshots(snapshot_dir)
    if not snapshots:
        print(f"No snapshots found in {snapshot_dir}")
        return 1

    import sqlite3

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    mismatches = []
    try:
        for table, payload in snapshots.items():
            ids = payload["ids"]
            expected = payload["rows"]
            actual = fetch_rows(conn, table, ids)
            if expected != actual:
                mismatches.append(table)
                print(f"Mismatch in {table}:")
                print(f"  expected rows: {len(expected)}")
                print(f"  actual rows:   {len(actual)}")
                for exp, act in zip(expected, actual):
                    if exp != act:
                        print(f"  id {exp.get('id')} differs")
                        for field in TABLE_FIELDS[table]:
                            if exp.get(field) != act.get(field):
                                print(
                                    f"    {field}: expected={exp.get(field)!r} actual={act.get(field)!r}"
                                )
                        break
        if mismatches:
            print("\nTables with mismatches:", ", ".join(mismatches))
            return 1
    finally:
        conn.close()

    print("Snapshots match current database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
