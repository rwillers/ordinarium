# Phase 9 deployment paths

## Scope

The `cloudflare-staging` and `cloudflare-production` GitHub environments are
Actions deployment gates and secret scopes for their corresponding Cloudflare
runtimes. They do not themselves create Workers, D1 databases, queues,
hostnames, or container fleets.

Labeled per-PR Cloudflare environments are intentionally deferred. Pull requests
run all validation without receiving deployment credentials or changing remote
resources.

## Pull request validation

Pull requests run these independent checks:

- the full Python and SQLite suite, with D1 and container contract tests called
  out as a separate step;
- TypeScript typechecking and Worker behavior tests;
- all three role-image builds; and
- a health, non-root, dependency, and clean-shutdown smoke test for every role
  image.

No pull-request workflow contains a Wrangler deployment command or references a
Cloudflare deployment environment.

## Staging deployment

Every commit merged to `main` runs `Deploy Cloudflare staging` serially through
the `cloudflare-staging` GitHub environment. The job:

1. checks out and verifies the exact triggering commit;
2. reruns Worker behavior tests;
3. verifies the six staging queues;
4. applies compatible remote D1 migrations and executes a read-only D1 probe;
5. deploys the alert classifier before the application Worker;
6. builds and pushes commit-tagged images for all four container roles, resolves
   their immutable registry digests, and renders a staging configuration pinned
   to those exact digests;
7. deploys the pinned configuration with an immediate container rollout;
8. probes `/health` and the login form through a Cloudflare Access service token
   on every readiness attempt to wake the named web container, then waits until
   every container application's configured digest and active or healthy
   instance state match the pinned configuration and verifies that the web
   application's serving digest also matches; and
9. uploads a 90-day `staging-release-<commit>` manifest.

The release manifest binds the Git commit to both Worker version IDs and all four
Cloudflare Registry image references. Every image must use an immutable
`@sha256:` digest and must equal the commit-tagged image built by that workflow
run. A staging workflow is successful only after two stable matching samples,
container health, the user-facing serving-image check, the manifest capture, and
the side-effect-free readiness checks all pass.

## GitHub staging environment

Configure `cloudflare-staging` for deployments from `main` with:

- environment variable `CLOUDFLARE_ACCOUNT_ID`;
- secret `CLOUDFLARE_API_TOKEN` with the Worker, Containers, D1, and Queues
  permissions required by Wrangler;
- secret `CLOUDFLARE_ACCESS_CLIENT_ID`; and
- secret `CLOUDFLARE_ACCESS_CLIENT_SECRET`.

The Access values belong to a service token permitted by the existing staging
Access application. They are used only for read-only post-deployment probes.

## Production promotion

`Promote Cloudflare production` is manual and fail-closed. The operator supplies
the successful staging workflow run ID, its exact 40-character commit SHA, and
the explicit word `PROMOTE`. The verification job then confirms:

- the referenced run is a successful `main` staging deployment;
- its head SHA equals the requested commit;
- the commit remains an ancestor of `main`;
- the matching staging manifest exists; and
- every container reference is pinned by digest.

The deploy job is disabled while the repository variable
`ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY` is not `true`. Production is now live on
Cloudflare; the variable may remain `false` between planned promotions as an
additional operational lock. The `cloudflare-production` environment must
require approval.

When enabled, the workflow checks out the staging-tested commit and renders a
production configuration with separate Worker, Durable Object, container, D1,
queue, and alert names. It uses the image digests from staging rather than
rebuilding images. Production migrations precede deployment, and the workflow
finishes with D1 and public health checks.

Required production environment variables are:

- `CLOUDFLARE_ACCOUNT_ID`
- `PRODUCTION_APP_DOMAIN`
- `PRODUCTION_D1_DATABASE_ID`
- `PRODUCTION_TURNSTILE_SITE_KEY`
- `PRODUCTION_ALERT_EMAIL_TO`

The environment also requires `CLOUDFLARE_API_TOKEN`. Application runtime
secrets must be provisioned on the production Workers before the repository
enable flag is changed.

## Operational policy

Production promotion remains manual. Cloudflare Git integration remains
disabled; GitHub Actions is the deployment authority. The retired Lightsail
workflow, environment, variables, and secrets are not part of this deployment
path.

## Production promotion runbook

Use this sequence for every production release:

1. Merge the intended release to `main`. Record the exact 40-character commit
   SHA.
2. Open the `Deploy Cloudflare staging` run triggered by that `main` commit.
   Wait for `Migrate, deploy, and verify staging` to succeed. Do not use a run
   from a branch, a different SHA, or a previously generated manifest.
3. Confirm the run uploaded `staging-release-<commit>`. A successful repaired
   workflow means the manifest contains the exact digests built in that run;
   readiness cannot substitute an older stable digest.
4. Verify the release behavior at `https://staging.ordinarium.com`, including
   the user-visible change being released. Automated health checks are necessary
   but do not replace this feature verification.
5. Temporarily set the repository variable
   `ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY` to `true`.
6. Dispatch `Promote Cloudflare production` with the successful staging run ID,
   the exact commit SHA, and confirmation value `PROMOTE`. Approve the
   `cloudflare-production` environment when prompted.
7. Wait for both `Verify staging-tested release` and `Promote exact release to
   production` to succeed. The production job deploys the staging digests with
   an immediate rollout and rechecks the configured and serving images.
8. Verify `https://ordinarium.com/login` and the released production behavior.
   For a UI release, use a hard refresh or a private window to rule out browser
   asset caching.
9. Restore `ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY` to `false` after verification.
   Record the staging run ID, production run URL, SHA, and verification result in
   the release handoff.

If staging or production reports an unexpected digest, stop. Do not rerun an old
production promotion because it reuses the same manifest. Correct the rollout,
run `Deploy Cloudflare staging` again, verify the newly generated manifest and
feature behavior, and promote that new staging run. Database migrations are
forward-only operational state and must be assessed separately from a Worker or
container rollback.

## Digest-capture incident guard

Cloudflare updates Worker code immediately but rolls container instances
separately, as described in Cloudflare's
[container rollout documentation](https://developers.cloudflare.com/containers/platform-details/rollouts/).
`wrangler containers list` can therefore expose an older serving or
summary image while the per-application configuration already targets a newer
digest, particularly for dormant queue containers. Release metadata must never
be derived from that list image alone.

The staging workflow uses `prepare_release_images.py` to establish the expected
digests before deployment. `verify_staging_deployment.py` then reads each
application's detailed configuration and health, compares it with those expected
digests, and separately requires the public web container's serving image to
match. `deployment_manifest.py` receives only that verified snapshot.
