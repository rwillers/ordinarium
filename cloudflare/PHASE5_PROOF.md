# Phase 5 web application port proof

Verified on July 18, 2026.

## Deployment

- Worker: `ordinarium-app-staging`
- Version: `5f74b766-ac5a-4d68-927d-319e283fde1c`
- Hostname: `containers-staging.ordinarium.com`
- Application database backend: D1 through the private `d1.internal` gateway
- Static files: Workers Static Assets, asset-first, retaining `/static/...` URLs
- Access: unchanged; unauthenticated requests to `/`, `/health`, and a static
  asset returned the expected Cloudflare Access login redirect
- Secrets installed: `PCO_TOKEN_ENCRYPTION_KEYS` and `OPS_HEALTH_TOKEN` (values
  were generated without being written to the repository or command output)

An authenticated staging session rendered the public landing page from the
deployed application. The page loaded `/static/styles/style.css` from the same
hostname, and the browser reported the stylesheet as active with the expected
computed font stack.

## Database boundary

Application modules no longer import or call `get_db()` directly. SQLite and D1
are both accessed through the database gateway contract. A small DB-API adapter
preserves the existing PCO transaction boundary while routing its operations
through that contract.

Alternate-backend isolation tests deliberately provide a fallback SQLite
connection with no application tables. Account, service, sharing, admin, and PCO
workflows still succeed, proving those paths use the configured gateway rather
than silently reaching the fallback database.

## Authentication and secrets

- New passwords use pinned Argon2id parameters: 19 MiB memory, two iterations,
  and one lane.
- Existing Werkzeug scrypt hashes remain valid and are rehashed to Argon2id after
  a successful login.
- Flask-Login, Flask-WTF, signed sessions, CSRF fields, route methods, redirects,
  filenames, and templates remain in place.
- PCO access and refresh tokens are written as versioned AES-GCM envelopes with
  fresh nonces and user/field-specific associated data.
- Legacy plaintext PCO tokens remain readable for migration. Unknown versions,
  malformed envelopes, and authentication failures are rejected rather than
  treated as plaintext.

## Health and assets

`/health` is handled by the Worker before container startup or D1 access. The
new `/ops/d1-health` route requires the deployment-specific bearer secret and
runs a minimal `select 1 as ok` against D1. Unauthorized requests are hidden with
a `404`; failed database checks return a controlled `503`.

The asset build copies Flask's existing static tree to the Worker asset bundle.
Wrangler's deployment dry run discovered all 19 assets, typechecked the Worker,
and built all four container images successfully with OrbStack.

## Compatibility verification

| Check | Result |
| --- | --- |
| Flask suite, SQLite gateway | 289 passed; known date-sensitive service-copy test excluded |
| Flask suite, alternate gateway | 288 passed; same service-copy test excluded; one pre-existing external-calendar test outside the route-test exit scope |
| Alternate-backend isolation | 6 passed with a deliberately unusable fallback database |
| Focused PCO tests | 48 passed |
| Worker tests | 8 passed |
| AWS normalized HTML snapshots | 4 matched (`/`, `/login`, `/signup`, `/reset-password`) |
| Git whitespace check | passed |

The AWS comparison normalizes only CSRF tokens and the environment-specific
Turnstile site key. All other HTML must match byte-for-byte after normalization.

The external-calendar test is not a Flask route test and has a pre-existing
order/app-context dependency: it fetches Google Calendar data and accesses the
liturgical cache outside an application context when run without another test
warming that cache. It is documented here but intentionally unchanged under the
phase's migration-only scope.

## Exit condition

Passed. Existing Flask route behavior passes with both database backends, and
the normalized public HTML snapshots match AWS. The D1-backed Phase 5 build is
deployed behind the unchanged staging Access policy. No production resource was
changed.
