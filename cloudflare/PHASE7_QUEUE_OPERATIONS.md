# Phase 7 queue operations

Run `npm run queues:ensure` from `cloudflare/` with an authenticated Wrangler
session before the first Phase 7 deployment. The command inspects each required
queue before changing anything, creates only queues that Wrangler explicitly
reports as missing, accepts a concurrent already-existing result, and then
verifies all four queues remotely. It fails closed when inspection or final
verification is incomplete.

The exact required queues are:

- `ordinarium-app-staging-pco-jobs`
- `ordinarium-app-staging-pco-jobs-dlq`
- `ordinarium-app-staging-email-jobs`
- `ordinarium-app-staging-email-jobs-dlq`

The two DLQ consumers preserve failed terminalization attempts for the platform
maximum of 100 delivery retries. This improves resilience during a temporary D1
or container outage, but finite queue retries cannot guarantee terminalization
after a prolonged outage. The scheduled D1 reconciliation republishes stale
`pending` rows (including a total initial publication failure) and expired
`running` claims. It deliberately excludes `retry` rows so Queue retry delays,
attempt limits, and DLQ transfer remain the single backoff authority. Queue
provisioning does not substitute for scheduled reconciliation.

## Required staging configuration and safe enablement order

Before deploying the Phase 7 Worker, verify these Wrangler secrets exist in the
staging environment:

- `SECRET_KEY`, `OPS_HEALTH_TOKEN`, and `DOCUMENT_SERVICE_AUTH_TOKEN` from the
  existing staging deployment.
- `PCO_TOKEN_ENCRYPTION_KEYS`, `PCO_CLIENT_ID`, and `PCO_CLIENT_SECRET` from the
  existing PCO integration. If the primary encryption version is not `v1`, also
  configure `PCO_TOKEN_ENCRYPTION_PRIMARY_VERSION`.
- Independent random `PCO_JOB_SERVICE_AUTH_TOKEN` and
  `EMAIL_JOB_SERVICE_AUTH_TOKEN` values.
- `PASSWORD_RESET_DELIVERY_KEY`, generated independently of every other key and
  encoded as base64 for exactly 32 random bytes. Expose it only to the web and
  email job roles.
- `MAILERSEND_API_TOKEN`, `MAILERSEND_FROM_EMAIL`, and
  `MAILERSEND_FROM_NAME`, with the sender identity already verified by
  MailerSend.

Verify these non-secret staging variables in `wrangler.jsonc`:

- `DEPLOYMENT_ENV=staging`
- `APP_ORIGIN=https://staging.ordinarium.com`
- `SIDE_EFFECTS_HOSTNAME=staging.ordinarium.com`
- `EXTERNAL_SIDE_EFFECTS_ENABLED=false` during configuration checks

Use this order: provision and verify the four queues; verify D1 migration `0004`
and its `password_reset_requests` table; install and independently verify every
secret and sender identity above; run the Worker tests and Wrangler dry-run;
then deliberately change `EXTERNAL_SIDE_EFFECTS_ENABLED` to `true` and deploy
before requesting a test reset email. Do not submit password-reset requests to a
deployment whose gate is `false`: the email processor treats the disabled gate
as a terminal configuration failure and clears the encrypted delivery material,
so enabling the gate later cannot recover that request.

## Password reset delivery semantics

Password-reset queue messages contain only `{reset_id}`. The encrypted delivery
token remains in D1 until MailerSend returns a successful response, the link is
used or expires, or processing reaches a terminal failure. A `202` response with
`x-message-id` is recorded as `sent`; a `202` response without that required
provider identifier is recorded as terminal `suppressed`; other successful 2xx
responses are recorded as terminal `accepted`. The scheduled reconciler
republishes stale initial `queued` records and expired `sending` leases; ordinary
`retry` records remain owned by Queue backoff and DLQ delivery.

MailerSend's email endpoint does not provide a provider idempotency key. A process
crash after provider acceptance but before the D1 success update can therefore
produce a duplicate reset email on retry. All other duplicate deliveries are
suppressed by the D1 claim and terminal-state checks.
