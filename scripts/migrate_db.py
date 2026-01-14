#!/usr/bin/env python
import sqlite3
from pathlib import Path


def get_db_path():
    from ordinarium import create_app

    app = create_app()
    return app.config["DATABASE"]


def ensure_schema_migrations(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          id INTEGER PRIMARY KEY,
          filename TEXT UNIQUE NOT NULL,
          applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def applied_migrations(conn):
    rows = conn.execute("select filename from schema_migrations").fetchall()
    return {row[0] for row in rows}


def apply_migration(conn, path):
    sql = path.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.execute(
        "insert into schema_migrations (filename) values (?)",
        (path.name,),
    )


def main():
    db_path = get_db_path()
    migrations_dir = Path(__file__).resolve().parent / "migrations"
    if not migrations_dir.exists():
        raise SystemExit(f"Migrations directory not found: {migrations_dir}")
    migration_files = sorted(migrations_dir.glob("*.sql"))
    if not migration_files:
        print("No migrations found.")
        return

    conn = sqlite3.connect(db_path)
    try:
        ensure_schema_migrations(conn)
        applied = applied_migrations(conn)
        for path in migration_files:
            if path.name in applied:
                continue
            apply_migration(conn, path)
            conn.commit()
            print(f"Applied {path.name}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
