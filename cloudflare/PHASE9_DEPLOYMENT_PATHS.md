# Phase 9 deployment paths

## Scope

Phase 9 keeps the existing Cloudflare staging runtime. The `cloudflare-staging`
GitHub environment is only an Actions deployment gate and secret scope; it does
not create another Worker, D1 database, queue set, hostname, or container fleet.

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
6. builds and deploys the static assets and four container roles;
7. waits for all container applications, then verifies `/health` and the login
   form through a Cloudflare Access service token; and
8. uploads a 90-day `staging-release-<commit>` manifest.

The release manifest binds the Git commit to both Worker version IDs and all four
Cloudflare Registry image references. Every image must use an immutable
`@sha256:` digest. A staging workflow is successful only after the manifest and
the side-effect-free readiness checks pass.

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
`ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY` is not `true`. Enabling it is part of the
later production cutover gate, after the `cloudflare-production` environment,
production D1 database, queues, Turnstile configuration, Worker secrets, and
domain are ready. That environment must require approval.

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

Production promotion remains manual after cutover. Automatic staging-to-
production promotion should be considered only after several uneventful manual
releases. Cloudflare Git integration remains disabled; GitHub Actions is the
deployment authority.
