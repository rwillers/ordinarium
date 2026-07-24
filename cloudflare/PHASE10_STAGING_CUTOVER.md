# Phase 10 staging cutover

Phase 10 replaces the abandoned Python Worker staging experiment with the
container-backed staging application. The experimental environment is
disposable: it is not a data source, configuration source, archive, or rollback
target for production. The eventual production migration source is the current
AWS production environment.

## Verified inventory

The following resources belong only to the abandoned experiment:

- Worker `ordinarium-worker-staging`
- Worker `ordinarium-pdf-staging`
- D1 database `ordinarium-staging`
  (`d7cd0eb3-eda6-4223-89e3-2141e8dad2bf`)
- Queue `ordinarium-staging-pco-jobs`
- Queue `ordinarium-staging-pco-jobs-dlq`
- Queue `ordinarium-staging-email-jobs`
- Queue `ordinarium-staging-email-jobs-dlq`
- Access applications for the legacy Worker's production and preview
  `workers.dev` hostnames
- Remote Git branch `staging` and its legacy branch/build configuration

Before the cutover, both legacy primary queues reported zero realtime backlog
and zero consumer lag. Both legacy dead-letter queues were inactive with no
current operations. None of the legacy resource names overlap the
`ordinarium-app-staging-*` container resources.

## Cutover

The deployment configuration makes `staging.ordinarium.com` the only custom
domain for `ordinarium-app-staging`. The same hostname is used for:

- GitHub deployment environment links and readiness probes
- application origin and side-effect authorization
- Turnstile hostname validation

The existing Cloudflare Access application and the `Ordinarium staging`
Turnstile widget remain in place. The Turnstile widget covers the
`ordinarium.com` zone.

Merge this change to `main` to deploy the container release to the canonical
hostname. Verify the authenticated readiness probe and the complete staging
workflow before deleting the legacy resources.

## Cleanup

After the canonical deployment passes:

1. Delete both legacy Workers.
2. Delete all four legacy queues.
3. Delete the legacy D1 database without export or retention.
4. Revoke legacy Python Worker credentials and remove obsolete GitHub values.
5. Delete the two legacy Worker Access applications and remove the temporary
   `containers-staging.ordinarium.com` destination from the retained `staging`
   Access application.
6. Delete the remote `staging` branch and its legacy branch/build configuration.
7. Delete legacy-only Worker versions and container images.

Do not remove Worker `ordinarium-app-staging`, Worker
`ordinarium-alerts-staging`, D1 database `ordinarium-app-staging`, or any
`ordinarium-app-staging-*` queue.

## Exit criterion

Phase 10 is complete when:

- `staging.ordinarium.com` serves `ordinarium-app-staging`;
- Access, Turnstile, authentication, password reset, application workflows,
  exports, queues, and container restarts pass;
- every resource belonging only to the abandoned staging experiment is gone;
- no experimental staging data or infrastructure is retained or referenced as
  a production migration or rollback source.
