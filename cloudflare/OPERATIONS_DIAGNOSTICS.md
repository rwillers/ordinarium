# Production diagnostics and paging policy

This document records the operating principles for diagnosing Ordinarium's
Cloudflare Worker, Containers, D1, Queue, and alert-delivery failures. Keep it
current as the platform and operational evidence change.

## Fixed principles

- Diagnose from retained logs and correlated identifiers before changing
  runtime behavior or suppressing an alert signature. State inferences as
  inferences until the underlying invocation is inspected.
- Page only for truly critical conditions. Do not send routine warning emails,
  warning digests, crawler summaries, or recovery chatter.
- Do not change any Container `sleepAfter` setting as part of incident tuning.
  Improve readiness, routing, retry, classification, and platform controls
  without altering the established container lifecycle policy.
- Use the strongest available diagnostic and security control. Prefer Workers
  Observability for historical invocations, Wrangler for authenticated CLI
  inspection, deployment logs for release state, and Cloudflare WAF before
  application-maintained probe lists.
- If the required account session or credentials are stale or unavailable,
  stop the affected investigation and ask the operator to restore access. Do
  not replace missing evidence with assumptions.
- Preserve sanitized telemetry. Never place exception messages, request
  headers, tokens, email addresses, or provider response bodies in alert email
  payloads.

## What qualifies for paging

A page should identify an actionable incident with evidence of current or
credible imminent impact. Examples include:

- repeated failures affecting legitimate user routes after configured retries;
- a failed production health or readiness check correlated with runtime errors;
- CPU or memory exhaustion, a missing Worker script, or a non-recovering
  Container failure;
- D1 write failures or persistent D1 read failures after safe retries;
- dead-lettered work, failed security controls, or an unavailable alert
  delivery path where work may be lost; and
- a confirmed security incident rather than an ordinary rejected probe.

A lone recovered transient, a known Container lifecycle alarm, an obvious
automated exploit probe, or an exception without evidence of impact is retained
in observability but does not page.

## Required access

Historical Worker diagnosis requires one of these authenticated paths:

1. a signed-in Cloudflare Dashboard session with access to the Ordinarium
   account and Workers Observability; or
2. an authenticated Wrangler session or narrowly scoped API token with Workers
   Observability read access.

The dashboard session is preferred for interactive investigation. No password,
global API key, or token should be copied into chat or committed to the
repository. Workers Logs retention is finite, so restore access before the
relevant interval expires.

The connected Workers Observability integration can currently read retained
invocations and Worker metadata. Its API identity is not authorized to manage
zone WAF rules, so a signed-in dashboard session is still required for that
configuration. Treat either connection as stale if an authorization check
fails, and ask the operator to restore it rather than working around it.

## Diagnostic workflow

1. Record the alert's UTC occurrence time, kind, request ID, route, status,
   container role, and deployment environment.
2. Query Workers Observability for the exact interval around the event. Inspect
   the invocation trigger, entrypoint, execution model, outcome, exceptions,
   structured logs, wall time, and related Durable Object or Queue context.
3. Correlate request IDs and timestamps across the application Worker,
   Container, D1 bridge, Queue consumer, Tail Worker, and alert delivery path.
4. Check the deployed Worker version, Container generation, rollout state, and
   GitHub deployment run before attributing the failure to current source.
5. Run bounded read-only production probes for `/health`, `/`, `/login`, and
   the affected legitimate route. Do not replay state-changing requests.
6. Classify the event as user impact, recovered platform transient, expected
   lifecycle behavior, crawler/probe traffic, release behavior, or unresolved.
7. Change code, configuration, or alert policy only after the evidence supports
   that classification. Add a regression test for each accepted signature.

If step 2 cannot be completed because authentication is missing, stop and ask
the operator to sign in while the retained logs are still available.

## Probe and exploit traffic

Cloudflare WAF is the primary control for obvious exploit traffic because it
can reject requests before they consume Worker or Container resources. Review
the active managed ruleset and add a narrowly scoped custom rule for server
technologies Ordinarium cannot serve.

The Worker also rejects a conservative set of impossible application paths as
defense in depth: foreign server-side extensions, sensitive environment or VCS
dot-paths, and unmistakable foreign-platform prefixes. These requests receive
a quiet, non-cacheable 404 and sanitized informational telemetry. They never
produce alert emails.

Keep the Worker list deliberately small. Prefer Cloudflare-managed coverage for
new exploit signatures, and add a local pattern only when it is impossible for
the Flask application to serve and is covered by tests.

### Active zone control

As of 2026-10-29, the `ordinarium.com` Free zone has one active custom security
rule named `Block impossible application probes` with the Block action:

```text
(http.request.uri.path.extension in {"asp" "aspx" "cgi" "jsp" "phar" "php" "phtml"}) or (http.request.uri.path eq "/" and any(url_decode(http.request.uri.args["gf_page"][*])[*] eq "upload"))
```

The dashboard reports one of five custom-rule slots used and no managed WAF
rules available on the current plan. A live verification returned 403 for the
observed PHP uploader and XML-RPC probes while `/` continued to return 200;
Workers Observability recorded no application-Worker invocation for either
blocked probe.

## 2026-08-14 overnight evidence baseline

Workers Observability confirmed all three emailed critical alerts used Worker
version `096af12c-8bd6-4da3-ba2d-61af50a50a08`:

- 04:45:37Z was a canceled `WebContainer.fetchWithReadiness` RPC with
  `ReadableStream received over RPC disconnected prematurely.` The associated
  `POST /xmlrpc.php` completed with 405 in 104 ms.
- 06:05:59Z had the same canceled readiness-stream signature. In the same
  sequence, `/`, `/about`, `/login`, and `/signup` completed with 200 in
  218-276 ms and the trailing `POST /` completed with 405 in 205 ms.
- 06:37:07Z was `GET /assets/file-uploader/server/php/index.php`, an impossible
  PHP uploader probe. It exhausted Container transient retries and returned 503
  after 1.78 seconds.

No failed legitimate route or current outage was confirmed. The exact canceled
readiness-stream signature is telemetry-only; other premature-stream contexts
remain critical. Primary queue backlog is also telemetry-only, while dead-letter
work remains critical.

## 2026-08-21 and 2026-08-22 incident evidence

Production emitted seven identical alert emails on 2026-08-21 from Worker
version `a967a7b8-fc2e-4faf-9840-83e9db5bd1fe`, release `ece79d2`. Each was a
`WebContainer` Durable Object alarm whose lifecycle callback reported:

```text
Connection closed: this Durable Object instance is no longer active. Reconnect or retry the request.
```

The stack consistently passed through `ContainerState.update`,
`ContainerState.setStatusAndupdate`, and `ContainerState.setStopped`. No
production 5xx response was present in the inspected window, and bounded live
checks of `/`, `/login`, and `/health` returned 200. This exact message is
therefore telemetry-only only when all of the Durable Object, `WebContainer`,
alarm, and lifecycle-stack conditions match. The same message in any other
context remains a critical runtime failure.

Staging emitted recurring D1 pages on 2026-08-22 from Worker version
`1ab0eb19-a847-4f98-8fb5-723ed834c781`, also release `ece79d2`. Retained logs
showed the `* * * * *` cron, not a user request, repeatedly failing with:

```text
D1_ERROR: D1 DB is overloaded. Requests queued for too long.
```

The application request traffic visible in the incident window was limited to
internal alert delivery. Unauthenticated staging access still redirected to
Cloudflare Access, there were no PCO reconciliation rows, only three password
reset rows, and direct inspection queries were fast. The evidence therefore
does not support legitimate user or test traffic as the cause. The minute cron
was launching the PCO and password-reset recovery scans concurrently, creating
three D1 reads per minute even when there was no work.

The remediation keeps queue metrics on the minute schedule. On each
five-minute boundary, scheduled orchestration first performs one bounded write
to terminalize expired password resets. When recovery is enabled, it then runs
the PCO recovery read and publication followed by one password-reset recovery
read and publication. Safe reconciliation reads use bounded jittered retries
at 250 ms, 1 second, and 2.5 seconds for recognized transient D1 failures,
including both documented overload messages. Writes are never automatically
retried. An exhausted retry still propagates to the Tail Worker and pages as a
D1 failure.

The first staging rollout of this remediation, workflow run `32590682159`,
also encountered overload code 7429 while Wrangler queried the remote migration
state. It stopped before any Worker or Container deployment. Staging and
production now run idempotent Wrangler D1 migration and verification commands
through the same kind of bounded, jittered, overload-only retry gate;
authentication, migration syntax, and all other failures still stop
immediately.

After deployment, the 18:35, 18:40, and 18:45 staging recovery ticks still
exhausted all four attempts of the first PCO read. The intervening metric-only
cron invocations were successful, and the identical SQL returned no rows from
the same D1 primary in 0.2 ms through the Cloudflare API. This isolates the
remaining failure to the staging Worker's D1 binding path rather than user
traffic or query cost. As a reversible circuit breaker, staging initially
disabled the two recovery reads and publications while retaining the
five-minute expired-password-reset cleanup write, normal Queue delivery, and
per-minute queue metrics. Production explicitly retained the full five-minute
orchestration. Do not reset or replace the staging database solely for this
platform-path failure.

The first circuit-breaker rollout, workflow run `32591901016`, stopped before
deployment when Wrangler's migration-state query returned Cloudflare internal
error code 7500. Because code-only releases do not need to query migration
state, staging now applies and verifies D1 migrations only when the pushed
commit changes `migrations/d1`; manual workflow runs continue to force the
check. Any schema-changing release therefore remains fail-closed, while an
unrelated D1 control-plane fault cannot block an operational Worker fix.

### Resolution and acceptance record

Pull requests [#45](https://github.com/rwillers/ordinarium/pull/45) through
[#48](https://github.com/rwillers/ordinarium/pull/48) merged the alert
classification, D1 read resilience, deployment retry, staging circuit-breaker,
and conditional migration-check changes. Staging workflow run
[`32592110561`](https://github.com/rwillers/ordinarium/actions/runs/32592110561)
successfully deployed the immutable release at commit
`6c1c53d32a2b65a34a73f2d4ceae830533750e68`. Between 18:58 and 19:05 UTC,
Workers Observability recorded seven consecutive staging cron invocations with
outcome `ok`, including both former five-minute recovery boundaries, and zero
`d1_reconciliation_retry` events.

Production promotion workflow run
[`32595518100`](https://github.com/rwillers/ordinarium/actions/runs/32595518100)
then verified the staging artifact and exact commit before deploying it through
the protected `cloudflare-production` environment. The production D1
migration, reconciled-data, alert-classifier, pinned-container, D1 readiness,
and public-readiness gates all completed successfully. The repository variable
`ENABLE_CLOUDFLARE_PRODUCTION_DEPLOY` was returned to `false` after promotion.

Independent post-deployment probes returned 200 for `/`, `/login`, and
`/health`. From 20:07 through 20:10 UTC, production recorded three scheduled
invocations with outcome `ok`, including the 20:10 five-minute recovery scan,
zero D1 reconciliation retries, and no alert-queue invocation. The production
Tail Worker processed 28 observed post-deployment batches with outcome `ok`.
Canceled `WebContainer.fetchWithReadiness` streams seen during the rollout were
expected Container readiness behavior and did not enqueue alerts.

### 2026-08-23 follow-up evidence and circuit-breaker correction

Staging continued to page approximately every 20 minutes after the initial
recovery-read circuit breaker. A Workers Observability inspection of
`2026-08-23T12:25Z` through `12:35Z` confirmed that the alert at
`2026-08-23T12:31:02.276Z` came from the `* * * * *` cron on Worker version
`74d7c7c2-5450-4328-91e3-82a01a2a9d10`, request ID `3APPCEJR5INJWYOE`, not
from a user request or the HTTP D1 bridge. The exception was `D1_ERROR: Network
connection lost.` and its stack passed through
`terminalizeExpiredPasswordResets`, `runSequentially`, and
`runScheduledReconciliation`. The failed cleanup merely deferred
terminalization of already-expired reset records. The alert-delivery Queue,
email-jobs Container, and MailerSend request then completed normally.

The remaining five-minute cleanup write was therefore bypassing the intended
staging D1 circuit breaker. When `SCHEDULED_RECONCILIATION_ENABLED=false`, the
Worker now skips all scheduled D1 maintenance, including expired-reset cleanup
and both recovery scans. Per-minute Queue metrics and normal Queue delivery
remain enabled. Production continues to set the flag to `true` and runs the
full cleanup and recovery sequence. Cron-originated D1 runtime failures are
classified as `d1-reconciliation`; other D1 runtime failures retain the
existing `d1-bridge` role.

For future diagnosis, retain these distinctions:

- A `* * * * *` trigger is scheduled system work, not evidence of a user or
  test request. Establish request-driven load only from HTTP triggers and
  correlated request identifiers.
- Staging currently sets `SCHEDULED_RECONCILIATION_ENABLED=false`; production
  explicitly sets it to `true`. In staging, this disables all scheduled D1
  maintenance on five-minute boundaries: expired-reset cleanup, PCO recovery,
  and password-reset recovery. If `d1_reconciliation_retry` or a cron-originated
  D1 failure appears in staging while the flag is false, the deployed
  configuration is stale or mismatched, or the event came from a different
  Worker version.
- Output from deployment-time `scripts/cloudflare/retry_d1_command.py` retries
  is CI log output, not `d1_reconciliation_retry` Worker telemetry. For generic
  D1 errors that do not carry that telemetry event name, continue checking
  deployment workflows, migration checks, HTTP requests, and Queue consumers
  as applicable to the failing operation.
- Fast direct D1 API queries do not prove the Worker binding path is healthy.
  If direct SQL remains fast while only Worker-binding reads exhaust bounded
  retries, treat the binding/platform path as the leading hypothesis and avoid
  resetting or replacing the database without contrary evidence.
- The inactive `WebContainer` lifecycle error is telemetry-only only when the
  Durable Object alarm, entrypoint, execution model, message, and a tested
  lifecycle or single `WebContainer.alarm` stack match. Near matches remain
  critical; see the October evidence below for the narrowly accepted variants.
- Re-enable staging scheduled reconciliation only after repeated Worker-binding
  operations succeed across multiple recovery boundaries. Normal Queue
  delivery and per-minute queue metrics remain enabled while the circuit
  breaker is active.

## 2026-10-26 through 2026-10-28 production triage

Authenticated Workers Observability inspection on October 28 correlated all five
runtime alert emails to `WebContainer` Durable Object alarms on application
Worker version `87895087-e766-45b7-97ec-60665a0fac4f`, release `af543a2`.
The same Durable Object ID appeared in all five invocations. These were not
HTTP or queue-delivery triggers:

| UTC occurrence | Platform exception | Invocation ID |
| --- | --- | --- |
| Oct 26 14:23:42.058 | Inactive Durable Object connection | `d34d63735e80998e3458127f212de0ae` |
| Oct 26 18:55:55.503 | Durable Object storage reset | `483bf099d6af3d7971ca6be8e31df8f9` |
| Oct 26 22:00:16.589 | Internal error with platform reference | `192af4594a75592e483e4ba483c65b95` |
| Oct 27 14:10:36.077 | Inactive Durable Object connection | `7bcaac640b9bf42ba7c0baa2aae530e3` |
| Oct 27 22:41:23.852 | Inactive Durable Object connection | `b48198b7b054493f01f7ac0c1ff23667` |

The inactive-connection and generic internal-error traces retained only
`at WebContainer.alarm (index.js:1407:28)`. The storage-reset trace included an
exception without a stack. These bypassed the previous classifier's required
`ContainerState` lifecycle frames. The classifier now accepts the single alarm
frame for the exact inactive or platform-reference messages, and an absent
stack only for the exact platform storage-reset message with a reference.
HTTP/RPC and cron triggers, other entrypoints, unknown/mixed exceptions,
CPU/memory failures, application stacks, and actionable telemetry still page.

A retained-telemetry search for October 26-27 returned no `status >= 500` or
`worker_request_failure` records; a positive-control `status = 200` search found
successful traffic. Searches also found no `d1_operation_failure`,
`d1_reconciliation_retry`, `queue_delivery_failure`, or
`queue_publication_failure` records. This supports a non-impacting platform
lifecycle interpretation, but does not establish Cloudflare's underlying cause
or guarantee that retention/sampling captured every request.

The October 28 08:29:22 UTC alert was `queue_metrics_failure` on the minute cron,
for `ordinarium-app-production-email-jobs-dlq`, invocation
`b4a36ec2dfc4ba38a05808759cfce2aa`. The next readings at 08:30:23 and 08:31:22
succeeded; the inspected 08:30 reading reported zero backlog bytes, count, and
oldest age. At approximately 19:22 EDT, both primary job queues and both DLQs
displayed zero realtime backlog and no ingestion/retry activity in the preceding
24 hours. The homepage, services list, and a liturgy view loaded successfully;
`/health` returned `{"status":"ok"}` but is edge-only. The running web container
used version 16 at 100% traffic. Both app and alert Workers identified release
`af543a2`, excluding a stale classifier release as the explanation for paging.

### Queue visibility paging policy

Raw `queue_metrics_failure` events remain sanitized telemetry. The Tail tracks
observations in dedicated `queue-metrics:<script>:<queue>` instances of the
existing `AlertDeduplicator` namespace, using a separate `metrics_health` key.
This survives Tail isolate restarts and requires no binding or migration.
Successful reads reset the streak. Three failed readings spanning at least two
minutes produce a critical `queue_failure` alert with category
`metrics_unavailable`; a gap over 150 seconds starts a new streak. Duplicate or
older observations cannot add failures or undo a newer recovery. Existing
15-minute alert deduplication applies. Only timestamp and health state are sent
to the monitor, which persists each newer observation's state.

If durable tracking fails or returns an invalid response, fail closed with a
critical `metrics_monitor_unavailable` alert. Delivery/publication failures,
D1 failures, and nonempty DLQ metrics still page immediately. Recovery sends no
email; observations do not replay jobs or change container `sleepAfter`.

Escalate correlated legitimate-route failures, failed readiness, or actual
dead-lettered work immediately. Escalate persistent platform alarm failures to
Cloudflare with UTC intervals, Worker versions, invocation IDs, and retained
platform references. Keep raw exceptions in authenticated observability, never
alert emails. Promote a reviewed, staging-tested release through the existing
production workflow, then independently recheck live behavior.

## 2026-10-29 Gravity Forms probe and request failure

The production email at `2026-10-29T18:50:37.625Z` identified request
`4b021971-2bce-491e-94cc-13ab4c1fda60`, route `/`, status 503, and category
`container_transient`. Authenticated dashboard inspection of retained Worker
logs in the approximately 18:02-19:02 UTC window correlated it with invocation
`0e6e9b86c677a63f18d221702deaa0a3`, trace
`fb9b42ebd855ddbd8c902ebfc3c8aaec`, and Worker version
`f1f2412a-c9c4-456b-b5ad-eb929c2b96c7`. The deployed release was
`cda1dffc88bde2a4eccf7f5fde35b5454ce8fbbf` (about 18 hours earlier).

The trigger was stateless `GET https://ordinarium.com/?gf_page=upload`.
Structured telemetry recorded three exhausted attempts, a controlled 503,
and 1490 ms duration; invocation wall time was 1493 ms with 7 ms CPU time.
The inspected hour contained one `worker_request_failure` event. The zone's
24-hour traffic overview also reported one 5xx response. Bounded live checks
of `/`, `/login`, and `/health` returned 200. Note that `/health` is served
at the edge; the successful homepage and login checks also exercised web
container routing.

The query identifies the legacy Gravity Forms upload endpoint documented in
the [vendor's release notes](https://www.gravityforms.com/blog/gravity-forms-v1-9-7-released/).
Ordinarium does not serve this WordPress plugin. Classify the request as a
foreign-platform probe, with no confirmed legitimate-user impact. Its exact
underlying container failure remains unresolved: the gateway aggregates
recognized platform HTTP failures and thrown RPC errors into the same
`container_transient` category. No container generation was established.
Do not describe this evidence as proving a cold start, D1 failure, or crash.

The existing active `Block impossible application probes` WAF rule was
extended with the narrowly scoped root-path Gravity Forms query condition
shown above. This rejects the probe before Worker or Container execution;
critical alerts for ordinary requests remain enabled. The local edge filter
also rejects this query with a quiet, non-cacheable 404 and sanitized
`foreign_platform_query` telemetry, including encoded values and repeated
parameters. That application fallback is a local change awaiting the normal
release process; the WAF rule is already live. Worker tests (117) and
TypeScript checks passed.

Final live verification returned 403 for the original query, an encoded
`gf_page=%75pload` value, an additional unrelated parameter, and a repeated
`gf_page=preview&gf_page=upload` query. `/`, `/login`, `/health`, and
`/?gf_page=preview` returned 200. The dashboard confirmed the updated rule
was Active. Its original foreign-extension condition remains in place.

## Session handoff checklist

For each troubleshooting session, record in the issue or pull request:

- the inspected time range and environment;
- whether Cloudflare Observability access was available;
- the invocation trigger and entrypoint;
- confirmed impact and affected legitimate routes, if any;
- the deployed version and Container generation;
- the evidence-backed classification;
- tests and controls changed; and
- any remaining fact that requires operator access.
