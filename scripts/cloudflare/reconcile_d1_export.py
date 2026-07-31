#!/usr/bin/env python3
"""Reconcile a remote D1 SQL export with a private migration manifest."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cloudflare.production_migration.contract import MIGRATED_TABLES
from scripts.cloudflare.production_migration.rehearsal import reconcile_manifest


def reconcile_export(manifest_path: Path, export_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target = sqlite3.connect(":memory:")
    target.row_factory = sqlite3.Row
    try:
        target.executescript(export_path.read_bytes().decode("utf-8"))
        result = reconcile_manifest(manifest, target)
    finally:
        target.close()
    return {
        "status": "passed",
        "contract_version": manifest["contract_version"],
        "migrated_table_count": len(MIGRATED_TABLES),
        "source_schema_migrations_applied": manifest["source_schema_upgrade"][
            "applied"
        ],
        "foreign_keys": result["foreign_keys"],
        "id_sequences": "ok",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_evidence(path: Path, evidence: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--d1-export", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = reconcile_export(args.manifest, args.d1_export)
    _write_evidence(args.evidence, evidence)
    print(
        "Remote D1 rehearsal reconciled "
        f"{evidence['migrated_table_count']} migrated tables."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
