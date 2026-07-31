# Deployment guide (Cloudflare)

Ordinarium is deployed to Cloudflare Workers, Containers, D1, and Queues. The
former Lightsail deployment path was retired after the Phase 11 production
cutover and must not be recreated from this repository.

## Validation and staging

Pull requests run the Python, SQLite, Worker, and container checks in GitHub
Actions. They do not receive deployment credentials and cannot change remote
Cloudflare resources.

Every commit merged to `main` runs `Deploy Cloudflare staging`. That workflow:

1. verifies the exact merged commit;
2. tests the Worker and container images;
3. applies compatible staging D1 migrations;
4. deploys the staging alert and application Workers;
5. checks queues, containers, `/health`, login, CSRF, and Turnstile; and
6. retains an immutable staging release manifest for 90 days.

The `cloudflare-staging` GitHub environment owns its Cloudflare and Access
credentials. Do not copy those secrets into pull-request workflows.

## Production promotion

Production promotion is manual and uses only a successful staging release. To
promote a release:

1. Find the successful `Deploy Cloudflare staging` run ID and its exact
   40-character commit SHA.
2. Confirm the repository variable `ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY` is
   `true`. It may remain `false` between planned promotions as an additional
   operational lock.
3. Run `Promote Cloudflare production` with the staging run ID, commit SHA, and
   the confirmation value `PROMOTE`.
4. Review and approve the protected `cloudflare-production` deployment.
5. Verify the public health endpoint and the affected application workflows.

The workflow rejects a failed or non-`main` staging run, a mismatched commit,
mutable container tags, missing secrets, or an empty production database. It
promotes the staging image digests rather than rebuilding them.

Production D1 contains live user writes. Do not roll traffic back to an old
SQLite database. Prefer a forward fix; any D1 Time Travel restore is a separate
destructive recovery decision.

## Configuration ownership

- `.github/workflows/deploy-cloudflare-staging.yml` owns automatic staging
  deployment.
- `.github/workflows/promote-cloudflare-production.yml` owns protected manual
  production promotion.
- `cloudflare/wrangler.jsonc` and
  `cloudflare/wrangler.alerts.jsonc` define the staging resources.
- `scripts/cloudflare/render_production_configs.py` renders production
  configuration from the tested release and protected environment values.
- `cloudflare/PHASE9_DEPLOYMENT_PATHS.md` documents the deployment controls and
  required GitHub environment configuration.
- `cloudflare/PHASE11_PRODUCTION_CUTOVER.md` records the migration and recovery
  boundaries.

Keep secrets out of the repository. Runtime application secrets and deployment
credentials belong only in their protected GitHub environments and Cloudflare
Worker secret stores.
