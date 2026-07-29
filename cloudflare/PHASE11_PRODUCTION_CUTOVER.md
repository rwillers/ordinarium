# Phase 11 production cutover

Phase 11 migrates the current AWS production application to the
container-backed Cloudflare production environment. The abandoned staging
experiment is not a source or rollback target. Current AWS production SQLite is
the only production data source.

The work is intentionally split into gates:

1. Build and test production migration tooling locally.
2. Provision and validate empty Cloudflare production resources.
3. Rehearse the migration from a current production snapshot without changing
   production traffic.
4. Enter a maintenance window, take the final snapshot, import and reconcile
   data, deploy the staging-tested release, and switch traffic.
5. Observe the new production environment and retire AWS only after the
   rollback window closes.

No gate authorizes the next one automatically.

## Gate 11A: migration tooling

The preparation command:

- takes a consistent SQLite backup, including committed WAL state;
- stores the snapshot and generated artifacts with private filesystem modes;
- runs SQLite integrity and foreign-key checks;
- rejects unknown tables and source/D1 schema drift;
- rejects unfinished Planning Center jobs, rows, operations, claims, and active
  service leases;
- emits deterministic, D1-compatible SQL with no explicit transaction;
- applies the SQL to a fresh local database initialized from every versioned D1
  migration;
- reconciles row counts and SHA-256 fingerprints for every migrated table;
- verifies foreign keys and numeric ID sequences; and
- writes a manifest containing counts and hashes, never row values or secrets.

Cloudflare limits individual SQL statements to 100 KB. The exporter writes one
row per statement and fails before producing a usable bundle if a row would
exceed that limit.

Run the command only after application writes have been stopped:

```sh
umask 077
./venv/bin/python scripts/cloudflare/migrate_production.py \
  --source /secure/path/ordinarium.db \
  --output-dir /secure/path/phase11-migration-YYYYMMDD-HHMM \
  --maintenance-confirmed
```

The output directory contains:

- `source-snapshot.sqlite3`, the private rollback and audit snapshot;
- `production-data.sql`, the D1 import file; and
- `manifest.json`, the preflight and local reconciliation evidence.

All three files contain sensitive production-derived information or metadata.
Keep the bundle outside the repository, do not upload it as a GitHub Actions
artifact, and store or destroy it according to the production backup policy.

## Data contract

The migration preserves durable application state:

- `users`
- `services`
- `pco_connections`
- `service_pco_links`
- `service_pco_item_links`
- `pco_batch_sync_jobs`
- `pco_plan_operations`
- `pco_batch_sync_rows`
- `service_shares`
- `service_custom_elements`
- `service_custom_templates`

Reference data is loaded from the versioned D1 migrations so it exactly matches
the deployed application release.

The following transient state starts empty:

- `pco_service_sync_leases`
- `pco_rate_limit_windows`
- `password_reset_requests`

Password-reset links issued before cutover will no longer work. Users can
request new links after production reopens.

## Remaining gates

Gate 11B will create the production D1 database, queues, Workers, routes,
Turnstile widget, secrets, alerting, and deployment variables while production
deployment remains disabled.

Gate 11C will use a fresh current-production snapshot to exercise the complete
remote import and reconciliation procedure against a disposable rehearsal D1
database. This is the first gate that needs production database access.

Gate 11D is the coordinated maintenance and traffic cutover. It requires a
human go/no-go decision after final data reconciliation and before DNS or route
changes.

Gate 11E covers post-cutover monitoring, rollback readiness, and eventual AWS
retirement.

## Gate 11A exit criteria

Gate 11A is complete when:

- focused migration tests pass;
- the full repository test suite passes;
- a representative source database produces a deterministic private bundle;
- the generated import reconciles exactly against a fresh local D1 schema; and
- the next required production input is documented before any external change.
