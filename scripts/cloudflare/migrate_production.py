#!/usr/bin/env python3
"""Prepare and locally rehearse the production SQLite-to-D1 data migration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cloudflare.production_migration.prepare import prepare


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a private SQLite snapshot, preflight it, generate D1 import "
            "SQL, and reconcile a local rehearsal."
        )
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--maintenance-confirmed",
        action="store_true",
        help="Confirm the source application is in maintenance/read-only mode.",
    )
    mode.add_argument(
        "--rehearsal-snapshot",
        action="store_true",
        help="Confirm the source is a consistent online-backup copy used only for rehearsal.",
    )
    args = parser.parse_args()

    migrations_dir = ROOT / "migrations" / "d1"
    source_migrations_dir = ROOT / "scripts" / "migrations"
    manifest = prepare(
        args.source, args.output_dir, migrations_dir, source_migrations_dir
    )
    total_rows = sum(value["rows"] for value in manifest["migrated_tables"].values())
    print(f"Preflight and local D1 rehearsal passed for {total_rows} rows.")
    print(f"Private migration bundle: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
