# Phase 8 security and observability proof

Verified on July 21, 2026.

## Deployment

- Application Worker: `ordinarium-app-staging`
- Application version: `4c6bc090-f7ca-4c70-ac98-f666df559488`
- Tail Worker: `ordinarium-alerts-staging`
- Tail Worker version: `10aa6bb3-6741-49d0-8b84-f766b7fd92cb`
- Alert recipient: `ryanwillers+ordo@gmail.com`
- Staging remains protected by Cloudflare Access. Production was not changed.

The alert deployment order is: provision and verify the alert queue and DLQ,
deploy `wrangler.alerts.jsonc`, and then deploy the application Worker that names
the Tail Worker as its consumer. This avoids attaching an application deployment
to a missing Tail Worker or queue.

## Security controls

- Login, signup, and reset submissions are rate-limited at the edge before a web
  container is invoked. Limits are 10 requests per minute for login and signup,
  and 5 requests per minute for reset requests.
- Each container receives only the secrets needed by its role. MailerSend and
  the alert recipient are available only to the email job role.
- Every container defaults to blocked internet access and has a role-specific
  hostname allowlist. MailerSend HTTPS is intercepted by the trusted Container
  proxy and forwarded only for `api.mailersend.com`; Python Requests trusts the
  ephemeral Cloudflare Container CA through `REQUESTS_CA_BUNDLE`.
- Turnstile remains restricted to the expected action and staging hostname.
- Alert messages have an exact, bounded schema and contain sanitized operational
  metadata only. Exception text, request headers, tokens, and email provider
  responses are not placed on the alert queue or in alert emails.

## Telemetry and alert delivery

Application telemetry emits bounded request, container, D1, queue, export, PCO,
and edge-security events. The dedicated Tail Worker converts the configured
failure events into alert messages and deduplicates identical fingerprints for
15 minutes with a Durable Object claim/commit protocol. Expected Durable Object
resets caused solely by deploying updated code are excluded from runtime-failure
alerts; all other runtime exceptions remain eligible.

The primary alert queue retries five times before moving a message to its DLQ.
The DLQ consumer makes up to 100 delivery attempts. The application Worker sends
validated alert messages to the private email job endpoint, acknowledges only a
terminal result, and preserves retryable provider or network failures.

The live test exercised both a natural web-container start and a bounded
synthetic warning message:

1. The application emitted `container_started` and the Tail Worker completed its
   dedupe claim and commit.
2. The Tail Worker published the alert to
   `ordinarium-app-staging-alerts`.
3. The first delivery attempt exposed a missing HTTPS interception path and was
   retained with a retry rather than acknowledged or lost.
4. After the allowlisted Container HTTPS proxy was deployed, MailerSend returned
   `202` and the queue emitted `queue_job_terminal` with disposition `accepted`.
5. Gmail received the exact synthetic alert ID
   `phase8-test-20260721T2322Z` at `ryanwillers+ordo@gmail.com`.

## Verification

| Check | Result |
| --- | --- |
| Python suite | 362 passed |
| Worker suite | 48 passed |
| Focused alert/container contracts | 6 passed |
| TypeScript typecheck | passed |
| Application Wrangler dry-run | passed |
| Tail Worker Wrangler dry-run | passed |
| OrbStack container builds | all four passed |
| Git whitespace check | passed |
| Authenticated staging request | `/login` returned 200 through Access |
| MailerSend delivery | provider returned 202; queue terminalized |
| Gmail receipt | exact synthetic alert ID received |

## Exit condition

Passed. Every Phase 8 plan item is implemented and tested on staging: Access,
edge auth limits, role-scoped secrets, default-deny egress, Turnstile validation,
structured sanitized telemetry, and operational email alerts. No production
resource was changed.
