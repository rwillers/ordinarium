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

Interactive staging verification has a separate authentication boundary. The
browser's Cloudflare Access session for `staging.ordinarium.com` is independent
of Dashboard, API, Workers Observability, and GitHub environment credentials. A
successful automated Access check therefore does not prove that the operator
can load staging interactively. Before production promotion, require a
successful user-visible staging check in the current browser session; if Access
redirects to sign-in, pause and restore that session before continuing.

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

As of 2026-08-14, the `ordinarium.com` Free zone has one active custom security
rule named `Block impossible application probes` with the Block action:

```text
(http.request.uri.path.extension in {"asp" "aspx" "cgi" "jsp" "phar" "php" "phtml"})
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
