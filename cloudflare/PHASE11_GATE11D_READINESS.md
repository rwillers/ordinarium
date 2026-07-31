# Phase 11 Gate 11D readiness

This note records pre-cutover readiness checks completed on July 31, 2026. It
does not authorize production data import, DNS changes, Worker deployment, or
the Gate 11D human go/no-go decision.

## Current production isolation

- `ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY` remains `false`.
- Cloudflare contains only the staging application and alert Workers; no
  production Worker is deployed.
- No production Worker custom domain is attached.
- The apex and `www` production hostnames each use direct AWS A and AAAA
  records. Both currently serve AWS and neither redirects to the other.
- All six production queues have zero producers and zero consumers.

## D1 rollback and target validation

- Production D1 supports Time Travel and returned a current bookmark through
  Wrangler.
- A fresh remote export passed the fail-closed empty-target validator:
  - expected versioned schema;
  - foreign keys;
  - empty migrated and transient application tables;
  - exact versioned reference data; and
  - initial numeric ID sequences.
- The temporary D1 export and sanitized validation evidence were deleted after
  the check.

## Readiness controls implemented

- Production Turnstile is enabled; only local development disables it.
- Production attaches both the apex and `www` custom domains to one Worker.
- `www` redirects to the canonical apex with HTTP 308 before application
  processing, preventing post-cutover split-brain writes to AWS.
- Production promotion fails before Worker deployment when D1 has no imported
  user data.
- Automated production readiness now requires stable pinned containers,
  `/health`, `/login`, CSRF, and the Turnstile widget.
- The empty-target validator emits only sanitized pass/fail evidence.

## Validation

- Gate 11C merged to `main` as `949f340` and its staging deployment completed
  successfully.
- All Worker behavior tests and TypeScript checks pass.
- Wrangler dry-run deployment and all four local container builds pass with
  OrbStack.
- The complete repository suite passes.

The next safe checkpoint is to merge and deploy this readiness increment to
staging, repeat the staging workflow tests on its exact commit, and then select
that successful run as the prospective Gate 11D release candidate.
