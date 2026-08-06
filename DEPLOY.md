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
2. tests the Worker;
3. applies compatible staging D1 migrations;
4. deploys the staging alert Worker;
5. builds and pushes commit-tagged container images, resolves their immutable
   registry digests, and deploys the application with those exact digests;
6. checks queues, probes `/health` and login to wake and validate the web
   container, then checks per-application configuration, active/healthy instance
   state, the running web instance generation, CSRF, and Turnstile; and
7. retains an immutable staging release manifest for 90 days.

Cloudflare updates Worker code immediately and container instances through a
separate rollout. The release gate therefore does not use a stable
`wrangler containers list` image as proof of the new release because that summary
can remain stale after the detailed application and running instance metadata
have advanced. It compares each application's detailed configuration with the
exact digest built by the current workflow and requires the running public web
instance generation to equal the configured application generation before
capturing the manifest. See Cloudflare's [container rollout documentation](https://developers.cloudflare.com/containers/platform-details/rollouts/).

The `cloudflare-staging` GitHub environment owns its Cloudflare and Access
credentials. Do not copy those secrets into pull-request workflows.

## Production promotion

Production promotion is manual and uses only a successful staging release. To
promote a release:

1. Find the successful `Deploy Cloudflare staging` run ID and its exact
   40-character commit SHA.
2. Confirm the user-visible release behavior on staging. Do not rely only on the
   automated health probe.
3. Temporarily set the repository variable
   `ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY` to `true`.
4. Run `Promote Cloudflare production` with the staging run ID, commit SHA, and
   the confirmation value `PROMOTE`.
5. Review and approve the protected `cloudflare-production` deployment.
6. Wait for both workflow jobs to succeed, then verify the login page and the
   affected production behavior. Use a hard refresh or private window for UI
   releases.
7. Restore `ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY` to `false` and record the
   staging run ID, production run URL, SHA, and verification result.

The workflow rejects a failed or non-`main` staging run, a mismatched commit,
mutable container tags, missing secrets, or an empty production database. It
promotes the staging image digests rather than rebuilding them.

If a digest check fails, do not rerun an old production promotion: it reuses the
same manifest. Correct the staging rollout, create and verify a new successful
staging run, and promote that run instead. The detailed operator checklist is in
the [production promotion runbook](cloudflare/PHASE9_DEPLOYMENT_PATHS.md#production-promotion-runbook).

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
