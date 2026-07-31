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

## Gate 11B: production resource and secret preparation

The empty production D1 database, queues, Turnstile widget, GitHub environment
variables, and application secrets are provisioned before production traffic
changes. `ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY` remains `false`, and neither the
production application Worker nor its custom domain is deployed during this
gate.

The application declares its complete runtime secret contract in
`cloudflare/wrangler.jsonc`. The production promotion workflow reads those
values only from the protected `cloudflare-production` GitHub environment,
writes them to a mode-0600 temporary JSON file on the ephemeral runner, rejects
missing or empty values, and passes that file to `wrangler deploy
--secrets-file`. Wrangler uploads the code, bindings, and secrets together as a
single Worker version. The temporary file is removed whether deployment
succeeds or fails.

This avoids an initial production Worker version that is routable without its
secrets. Existing secrets not present in a later bulk upload are not deleted,
but the declared required-secret contract prevents an incomplete deployment.

Gate 11B is complete when:

- the production D1 schema and reference data reconcile with all durable
  application tables empty;
- every production queue exists without producers or consumers;
- the production Turnstile widget is restricted to `ordinarium.com`;
- the protected GitHub environment contains every required variable and
  secret;
- the Cloudflare API token passes an end-to-end staging deployment;
- production secret handling and fail-closed tests pass; and
- `ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY` remains `false`.

## Gate 11C: disposable remote rehearsal

Gate 11C does not require a maintenance window. Take a consistent online
SQLite backup on AWS, copy it to a private local directory, and pass that copy
to the migration command with `--rehearsal-snapshot`. Never point rehearsal
mode at the live database file.

The migration command preserves the online backup as `source-snapshot.sqlite3`
and creates a hidden working copy. Pending versioned SQLite migrations are
applied only to the working copy before preflight and export. This allows the
legacy AWS schema to be normalized without changing AWS production. The hidden
copy is deleted on success or failure.

Schema parity compares the properties that constrain the explicit-row import:
column names, SQLite type affinity, nullability, and primary keys. Source-side
default expressions are not required to match because every exported column is
explicit and the D1 target owns post-cutover defaults.

Create a disposable ENAM D1 database, apply every D1 migration, and import the
generated `production-data.sql`. Export the remote database with `wrangler d1
export --remote`, then run:

```sh
./venv/bin/python scripts/cloudflare/reconcile_d1_export.py \
  --manifest /secure/path/rehearsal/manifest.json \
  --d1-export /secure/path/rehearsal/d1-export.sql \
  --evidence /secure/path/gate-11c-evidence.json
```

The reconciler compares deterministic row fingerprints for every migrated
table and verifies foreign keys and numeric ID sequences. Its evidence file
contains only pass/fail metadata and migration names, never row counts, row
hashes, or values.

After successful reconciliation, delete the disposable D1 database and the
entire production-derived rehearsal bundle. Retain only the sanitized evidence
and the repository proof note.

Gate 11C is complete when:

- the online AWS snapshot passes integrity, schema, and work-drain preflight;
- pending source migrations apply only to the private working copy;
- the local rehearsal reconciles exactly;
- the disposable remote D1 import and export reconcile exactly;
- the disposable D1 database and sensitive bundle are deleted; and
- AWS production, the production D1 database, Workers, routes, and DNS remain
  unchanged.

The completed rehearsal evidence is recorded in
`cloudflare/PHASE11_GATE11C_PROOF.md`.

## Gate 11D: coordinated production cutover

Gate 11D is a scheduled maintenance-window operation, not a routine deployment.
The final migration bundle remains on the operator's private workstation and is
never uploaded to GitHub Actions. The production promotion workflow consumes
only the successful staging release manifest and immutable container digests.

### Readiness before the maintenance window

Before scheduling the window:

- select a successful `Deploy Cloudflare staging` run and its exact `main`
  commit SHA;
- complete the authentication, password-reset, service editing, document
  export, queue retry, container restart, and Planning Center OAuth checks on
  that staging release;
- verify that production D1 still contains only the versioned schema and
  reference data, with every migrated and transient table empty;
- verify the production queues have no producers, consumers, or messages;
- record the current D1 Time Travel bookmark;
- inventory the current apex and `www` A/AAAA records needed for rollback; and
- leave `ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY=false` until final reconciliation
  has passed.

Export the still-empty production D1 database to a private temporary file and
run this fail-closed target check before entering the maintenance window:

```sh
umask 077
cloudflare/node_modules/.bin/wrangler d1 export \
  ordinarium-app-production \
  --remote \
  --output /secure/path/production-empty.sql
./venv/bin/python scripts/cloudflare/validate_d1_cutover_target.py \
  --d1-export /secure/path/production-empty.sql \
  --evidence /secure/path/production-empty-evidence.json
```

The check verifies schema parity, foreign keys, empty application and transient
tables, versioned reference data, and initial ID sequences. Its evidence does
not retain table contents, counts, or fingerprints.

Both `ordinarium.com` and `www.ordinarium.com` currently reach AWS directly.
The production configuration therefore attaches both hostnames to the same
Worker. Requests for `www` receive a 308 redirect to the canonical apex before
rate limiting, Turnstile, or container processing. This prevents split-brain
writes to AWS after the apex moves. Turnstile is enabled in both staging and
production and disabled only for local development.

### Maintenance-window sequence

1. Put AWS in maintenance/read-only mode and verify that application writes are
   blocked.
2. Drain Planning Center jobs, operations, rows, claims, and service leases.
3. Take the immutable final SQLite backup and run
   `migrate_production.py --maintenance-confirmed` against that backup.
4. Reconfirm that production D1 is empty, then import `production-data.sql`
   with Wrangler.
5. Export production D1 to the private bundle and run
   `reconcile_d1_export.py` against the final manifest.
6. Record the post-import D1 Time Travel bookmark. If reconciliation fails,
   stop, restore the pre-import empty bookmark, and reopen AWS without changing
   traffic.
7. Pause for the explicit human go/no-go decision. No DNS record or Worker
   custom domain changes before approval.
8. After approval, set `ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY=true` and dispatch
   `Promote Cloudflare production` with the selected staging run ID, commit SHA,
   and `PROMOTE`. Let its read-only release verification finish and pause at the
   protected `cloudflare-production` environment approval.
9. Remove the legacy apex and `www` A/AAAA records and immediately approve the
   waiting environment deployment. The workflow refuses to deploy if production
   data is still empty, promotes the pinned staging images, attaches both
   hostnames, and verifies D1, containers, `/health`, `/login`, CSRF, and the
   Turnstile widget.
10. Perform the complete production smoke test before reopening writes. Disable
    legacy AWS deployment and retain AWS read-only for at least seven days.

The DNS record removal and environment approval in step 9 are one coordinated
action. If the workflow fails before Cloudflare serves production, restore the
recorded AWS A/AAAA records and keep AWS authoritative.

### Rollback boundary

- Before any D1-backed user write, rollback is domain detachment plus restoration
  of the recorded AWS A/AAAA records, followed by reopening AWS writes.
- After D1-backed writes begin, do not send traffic back to the stale AWS
  database. Prefer a forward fix. If data recovery is necessary, D1 Time Travel
  can restore the database to a recorded bookmark, but restore is destructive
  and requires a separate explicit decision.

Gate 11D is complete when:

- the final private source snapshot and local rehearsal pass;
- production D1 imports and reconciles exactly;
- the human go/no-go is recorded after reconciliation;
- the staging-tested release serves both production hostnames with `www`
  redirecting to the apex;
- authentication, Turnstile, password reset, application workflows, exports,
  queues, container stability, alerting, and Planning Center OAuth pass; and
- AWS is read-only, rollback records and D1 bookmarks are retained, and no
  production-derived bundle has entered the repository or GitHub Actions.

The pre-cutover inventory and local implementation evidence are recorded in
`cloudflare/PHASE11_GATE11D_READINESS.md`. That note is not cutover approval.

## Gate 11A exit criteria

Gate 11A is complete when:

- focused migration tests pass;
- the full repository test suite passes;
- a representative source database produces a deterministic private bundle;
- the generated import reconciles exactly against a fresh local D1 schema; and
- the next required production input is documented before any external change.
