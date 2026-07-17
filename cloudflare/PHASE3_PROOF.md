# Phase 3 infrastructure proof

Verified on July 17, 2026.

## Environment

- Worker: `ordinarium-app-staging`
- Version: `d568a7b4-478c-470d-9c02-b52392856b59`
- Hostname: `containers-staging.ordinarium.com`
- Access: the hostname is a destination on the existing `staging` Access
  application and retains its tester and operational-check policies.
- Public bypass: disabled (`workers_dev = false`). An unauthenticated health
  request returned a Cloudflare Access login redirect before reaching the
  Worker.
- Persistence: the web startup command initializes a fresh SQLite database.
  This environment is disposable and must never be treated as authoritative.

## Local Cloudflare container proof

The complete Worker-to-web-to-document path was exercised with Wrangler and
OrbStack using the same Worker and container configuration as staging.

| Check | Result |
| --- | --- |
| Cold health request | 6,864.4 ms |
| Warm health request | 13.3 ms |
| PDF export | 43,072 bytes in 2,447.9 ms; `%PDF` signature |
| DOCX export | 44,748 bytes in 290.1 ms; ZIP/DOCX signature |
| Web memory after exports | 133.1 MiB |
| Document memory after PDF | 145.9 MiB |
| Document idle lifecycle | stopped successfully after the 60-second timeout |

The flow created a user, logged out, logged back in with the stored password
hash, created a service, and downloaded both exports. This covered Flask
sessions, Jinja rendering, Werkzeug password hashing, the web HTTP client, and
the CPython PDF/DOCX libraries without Python Worker compatibility code.

## Hosted staging proof

The Worker and all four container applications deployed successfully. Through
an authenticated Access session, the web container completed signup, logout,
password login, session persistence, and service creation. Signup completed in
1,374 ms and login completed in 1,179 ms on the observed run.

PDF and DOCX downloads both completed successfully through the hosted Flask
routes. Cloudflare reported the named `staging-documents` instance as running
after the downloads and `inactive` after its configured 60-second idle window.

## Exit condition

Passed. Existing Flask behavior and both exports work in the container
deployment without Python Worker compatibility code. SQLite in this proof
remains disposable and non-authoritative.

## Automated verification

- `pytest -q`: 264 passed
- `npm run typecheck`: passed
- `scripts/cloudflare/verify_phase2_images.sh`: passed for `linux/amd64`
- Git whitespace check: passed
