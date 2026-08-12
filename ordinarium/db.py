import sqlite3
from pathlib import Path

import click
from flask import current_app, g, has_request_context, request

from .infrastructure import D1HttpGateway, GatewayConnection, SQLiteGateway


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


def get_database_gateway():
    if "database_gateway" in g:
        return g.database_gateway

    factory = current_app.config.get("DATABASE_GATEWAY_FACTORY")
    if factory is not None:
        g.database_gateway = factory()
        return g.database_gateway

    backend = current_app.config.get("DATABASE_GATEWAY_BACKEND", "sqlite")
    if backend == "sqlite":
        g.database_gateway = SQLiteGateway(get_db())
        return g.database_gateway
    if backend == "d1":
        service_url = current_app.config.get("D1_SERVICE_URL")
        if not service_url:
            raise RuntimeError("D1_SERVICE_URL is required for the D1 gateway.")
        g.database_gateway = D1HttpGateway(
            service_url,
            timeout_seconds=current_app.config["D1_SERVICE_TIMEOUT_SECONDS"],
            max_response_bytes=current_app.config["D1_SERVICE_MAX_BYTES"],
            request_id=(
                request.headers.get("X-Ordinarium-Request-Id")
                if has_request_context()
                else None
            ),
        )
        return g.database_gateway
    raise RuntimeError(f"Unknown database gateway backend: {backend}")


def get_gateway_connection():
    if "gateway_connection" not in g:
        g.gateway_connection = GatewayConnection(get_database_gateway())
    return g.gateway_connection


def close_db(_exception=None):
    g.pop("gateway_connection", None)
    gateway = g.pop("database_gateway", None)
    if gateway is not None and hasattr(gateway, "close"):
        gateway.close()
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
