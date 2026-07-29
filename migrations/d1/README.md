# D1 migrations

These migrations initialize the fresh Cloudflare D1 persistence layer. Apply
them in filename order with Wrangler.

- `0001_baseline.sql` is a generated schema snapshot.
- `0002_reference_data.sql` contains generated application reference data. It
  intentionally excludes users and services.
- `0003_id_sequences.sql` adds collision-free numeric ID allocation.
- `0004_operational_state.sql` is the reviewed successor to the useful
  resilience state from the archived Python Worker experiment.
- `0005_legacy_id_sequence_sync.sql` prevents legacy SQLite-style ID writers
  from leaving sequences stale during the Phase 5 transition.

Regenerate the first two files from a freshly initialized main SQLite database:

```sh
./venv/bin/python scripts/cloudflare/generate_d1_baseline.py
```

The generator deliberately excludes `schema_migrations` and `id_sequences`.
The latter is maintained as an explicit cross-backend migration so its behavior
can be reviewed and tested independently.

Validate from an empty local D1 before applying remotely:

```sh
cd cloudflare
npx wrangler d1 migrations apply APP_DB --local --persist-to /tmp/ordinarium-d1
npx wrangler d1 migrations apply APP_DB --remote
```

Do not create or migrate `ordinarium-app-production` until staging validation is
complete.

Production data transfer and reconciliation are documented in
[`cloudflare/PHASE11_PRODUCTION_CUTOVER.md`](../../cloudflare/PHASE11_PRODUCTION_CUTOVER.md).
