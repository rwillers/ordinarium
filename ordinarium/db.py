import sqlite3
from pathlib import Path

import click
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        # Enforce FK constraints (disabled by default in SQLite).
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf-8"))
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          id INTEGER PRIMARY KEY,
          filename TEXT UNIQUE NOT NULL,
          applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    migrations_dir = Path(current_app.root_path).parent / "scripts" / "migrations"
    if migrations_dir.exists():
        for path in sorted(migrations_dir.glob("*.sql")):
            db.execute(
                "insert or ignore into schema_migrations (filename) values (?)",
                (path.name,),
            )
    db.commit()


@click.command("init-db")
def init_db_command():
    init_db()
    click.echo("Initialized the database.")
