# Phase 11 Gate 11D production proof

Gate 11D completed on July 31, 2026. The operator accepted the Cloudflare
production deployment after completing the planned manual test pass.

## Release and data

- Pull request `#27` merged the cutover-ready release to `main` at commit
  `08ce66bc2aafcc07d85d9a6cc50cca561548496b`.
- Staging run `30657000895` passed for that exact commit and produced an
  immutable release manifest.
- The final consistent AWS SQLite snapshot passed integrity, schema, migration,
  and work-drain preflight.
- All 11 migrated tables imported into production D1 and reconciled exactly.
- Production D1 Time Travel bookmarks were captured before and after the
  import, then discarded with the private bundle after the rollback hold was
  waived.

## Production acceptance

- Production promotion run `30658846054` completed successfully.
- `ordinarium.com` serves the production Worker and its health check passes.
- `www.ordinarium.com` redirects to the canonical apex while preserving the
  request path and query.
- Authentication, Turnstile, password reset, application workflows, exports,
  queues, container behavior, alerting, and Planning Center OAuth passed the
  operator's manual acceptance checks.
- Post-deployment logs contained no warning or error signal requiring rollback.

## Retirement decision

The former AWS deployment never reached general availability. The operator
therefore waived the planned seven-day rollback hold after manual acceptance
and authorized immediate cleanup. The retired GitHub Actions workflow and its
Lightsail-only credentials, variable, environment, and deploy key are removed
as part of this closeout. The private production-derived cutover bundle is
deleted after its sanitized evidence is recorded here.

Cloudflare production D1 is now the authoritative datastore. Once D1-backed
writes began, the supported recovery posture became forward-fix or an explicit
D1 Time Travel recovery decision; the retired AWS SQLite database is not a
traffic rollback target.
