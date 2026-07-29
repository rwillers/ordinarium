"""Orchestrate a private snapshot, preflight, export, and local rehearsal."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .contract import (
    CONTRACT_VERSION,
    EXCLUSION_REASONS,
    MIGRATED_TABLES,
    TRANSIENT_TABLES,
)
from .database import (
    apply_d1_migrations,
    connect_read_only,
    sha256_file,
    table_fingerprint,
    table_names,
)
from .export import write_export
from .preflight import run_preflight
from .rehearsal import rehearse


def prepare(source_path: Path, output_dir: Path, migrations_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    snapshot_path = output_dir / "source-snapshot.sqlite3"
    export_path = output_dir / "production-data.sql"
    manifest_path = output_dir / "manifest.json"
    export_path.unlink(missing_ok=True)
    manifest_path.unlink(missing_ok=True)
    _create_snapshot(source_path, snapshot_path)

    source = connect_read_only(snapshot_path)
    target_schema = sqlite3.connect(":memory:")
    target_schema.row_factory = sqlite3.Row
    try:
        apply_d1_migrations(target_schema, migrations_dir)
        checks = run_preflight(source, target_schema)
        write_export(source, export_path)
        rehearsal = rehearse(source, export_path, migrations_dir)
        manifest = _manifest(
            source, snapshot_path, export_path, migrations_dir, checks, rehearsal
        )
        _write_manifest(manifest_path, manifest)
        return manifest
    finally:
        target_schema.close()
        source.close()


def _create_snapshot(source_path: Path, destination: Path) -> None:
    source = connect_read_only(source_path)
    temporary = destination.with_suffix(".sqlite3.tmp")
    temporary.unlink(missing_ok=True)
    target = sqlite3.connect(temporary)
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()
    os.chmod(temporary, 0o600)
    temporary.replace(destination)


def _manifest(
    source,
    snapshot_path,
    export_path,
    migrations_dir,
    checks,
    rehearsal,
) -> dict:
    present_tables = table_names(source)
    excluded = {
        table: {
            "rows": _count_rows(source, table) if table in present_tables else 0,
            "reason": EXCLUSION_REASONS[table],
        }
        for table in sorted(TRANSIENT_TABLES)
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_snapshot": {
            "filename": snapshot_path.name,
            "sha256": sha256_file(snapshot_path),
        },
        "d1_migrations_sha256": _migrations_digest(migrations_dir),
        "data_export": {
            "filename": export_path.name,
            "sha256": sha256_file(export_path),
        },
        "migrated_tables": {
            table: table_fingerprint(source, table) for table in MIGRATED_TABLES
        },
        "excluded_tables": excluded,
        "reference_data": "Loaded from the versioned D1 migrations.",
        "preflight": checks,
        "local_rehearsal": rehearsal,
    }


def _count_rows(connection, table: str) -> int:
    return connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def _migrations_digest(directory: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.sql")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _write_manifest(path: Path, manifest: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)
