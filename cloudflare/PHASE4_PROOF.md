# Phase 4 D1 persistence proof

Verified on July 17, 2026.

## Resource boundary

- Fresh database: `ordinarium-app-staging`
- Database ID: `e13336d8-cf7c-4c63-955d-4d8c7cfa4321`
- Region: ENAM
- Deployed Worker version: `fc9f5141-9409-4974-94ab-8aa609525b0b`
- Archived experimental database: unchanged
- Production database: not created

## Architecture

Flask now has one synchronous database gateway contract with SQLite and D1 HTTP
implementations. The web container sends bounded, POST-only JSON operations to
`http://d1.internal/query`. Cloudflare's container outbound-host binding handles
that private hostname inside the Worker and executes prepared statements through
the `APP_DB` D1 binding. No public D1 endpoint or API token is used.

The bridge accepts only `fetch_one`, `fetch_all`, `execute`, `batch`, and
`allocate_id`. Results are normalized into backend-independent rows and mutation
metadata. D1 batch calls retain D1's transactional behavior.

The application remains configured for SQLite by default. Phase 4 moves the
signup/login timestamp and service-sharing SQL behind stores and provides a
gateway-native service creation store. Phase 5 will port the remaining route
families before changing the deployed application backend to D1.

## Schema and ID allocation

The D1 baseline and reference seed are reproducibly generated from a freshly
initialized main SQLite database. User and service records are excluded. A
reviewed operational migration retains password-reset delivery state and PCO
claim, lease, rate-limit, batch-row, and idempotency state from the archived
experiment without copying its migration chain wholesale.

Both backends allocate numeric IDs with an atomic update to `id_sequences` and
`RETURNING`. IDs are never reused; gaps after failed or deleted work are expected.
The SQLite migration seeds every sequence from the corresponding table's current
maximum ID, preserving existing AWS data during the transition. Insert triggers
also advance sequences for remaining legacy ID writers until Phase 5 ports them.

## D1 verification

All five migrations applied successfully to a pristine local D1 and the fresh
remote staging D1. The remote reference-state query returned:

| Check | Result |
| --- | ---: |
| Text rows | 1,295 |
| Page rows | 2 |
| Initial user rows | 0 |
| Initial service rows | 0 |
| Initial next user ID | 1 |

The real local network path was also exercised end to end. A Python process
inside Wrangler's web container used `D1HttpGateway` to call `d1.internal`; the
Worker bridge allocated IDs and wrote and joined a user, service, and share in
local D1. A D1 batch removed all three records, and a follow-up query confirmed
all proof tables were empty.

A remote representative workflow allocated numeric IDs atomically, inserted a
user, inserted an owned service, created a share, and read the three records back
through a join. Cleanup removed all proof records. The next user ID remained 2,
demonstrating the intentional no-reuse/gaps-allowed rule.

A second remote proof inserted an ID through the legacy path. The compatibility
trigger advanced the user sequence from 2 to 3; cleanup removed the proof row
without rewinding the sequence.

## Automated verification

- Full Flask suite: 276 passed
- Generated migration drift test: passed
- Clean SQLite and pristine local D1 migration tests: passed
- SQLite gateway CRUD, rollback, and allocation tests: passed
- D1 HTTP client response and error normalization tests: passed
- Worker bridge operation, bounds, metadata, batch, and allocation tests: passed
- Representative SQLite user/service/share store workflow: passed
- Local web container → private Worker bridge → D1 workflow: passed
- TypeScript typecheck and Worker/container deployment dry run: passed
- Staging Worker and all four container images deployed successfully
- Unauthenticated staging health probe: Access login redirect (expected)

## Exit condition

Passed. The entire Flask suite runs on the SQLite gateway, and representative
local and remote D1 workflows pass. Production remains intentionally untouched.
