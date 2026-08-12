import assert from "node:assert/strict";
import test from "node:test";

import { handleTailEvents } from "./alert_dispatch.ts";
import { claimAlert, commitAlert, releaseAlert } from "./alert_dedupe_policy.ts";
import {
  alertFingerprint,
  alertsFromTrace,
  parseOperationalAlert,
} from "./operational_alerts.ts";


const trace = (records = [], options = {}) => ({
  event: options.event || null,
  eventTimestamp: Date.parse("2026-07-21T12:00:00Z"),
  logs: records.map((record) => ({
    timestamp: Date.now(),
    level: "error",
    message: [record],
  })),
  exceptions: options.exceptions || [],
  diagnosticsChannelEvents: [],
  scriptName: "ordinarium-app-staging",
  entrypoint: options.entrypoint,
  outcome: options.outcome || "ok",
  executionModel: options.executionModel || "stateless",
  truncated: false,
  cpuTime: 1,
  wallTime: 2,
});


class FakeDeduplicatorNamespace {
  constructor() {
    this.states = new Map();
  }

  getByName(name) {
    return {
      fetch: async (request) => {
        const operation = new URL(request.url).pathname.slice(1);
        const payload = await request.json();
        const state = this.states.get(name);
        if (operation === "claim") {
          const result = claimAlert(
            state,
            payload.now,
            payload.window_ms,
            payload.token,
          );
          if (result.allowed) {
            this.states.set(name, result.state);
          }
          return Response.json({ allowed: result.allowed, token: result.token });
        }
        const next = operation === "commit"
          ? commitAlert(state, payload.token, payload.now)
          : releaseAlert(state, payload.token);
        if (next) {
          this.states.set(name, next);
        }
        return Response.json({ updated: next !== null });
      },
    };
  }
}


test("tail classification covers every Phase 8 alert category", () => {
  const records = [
    { event: "container_started", container_role: "web" },
    { event: "container_stopped", container_role: "documents", error_category: "container_failure" },
    { event: "worker_request_failure", route: "/service/123", status: 503 },
    { event: "d1_operation_failure", error_category: "internal" },
    { event: "queue_delivery_failure", queue: "pco", error_category: "timeout" },
    { event: "queue_metrics", queue: "pco", threshold_exceeded: true, dlq: false },
    { event: "queue_metrics", queue: "pco-dlq", threshold_exceeded: true, dlq: true },
    { event: "export_failure", request_id: "request-1" },
    { event: "pco_auth_failure", job_id: "job-1" },
    { event: "edge_rate_limit_failure", route: "/login" },
    { event: "turnstile_siteverify_failure", error_category: "network" },
  ];

  const kinds = alertsFromTrace(trace(records)).map((alert) => alert.kind);

  assert.deepEqual(kinds, [
    "container_failure",
    "worker_request_failure",
    "d1_failure",
    "queue_failure",
    "queue_backlog",
    "dead_letter",
    "export_failure",
    "pco_authorization_failure",
    "edge_security_failure",
    "turnstile_failure",
  ]);
});


test("routine container starts remain telemetry and do not enqueue alerts", () => {
  assert.deepEqual(
    alertsFromTrace(trace([{ event: "container_started", container_role: "web" }])),
    [],
  );
});


test("runtime failures are sanitized and raw exception text never crosses the queue", () => {
  const [alert] = alertsFromTrace(trace([], {
    outcome: "exception",
    exceptions: [{ name: "Error", message: "secret bearer token", timestamp: Date.now() }],
  }));

  assert.equal(alert.kind, "worker_runtime_failure");
  assert.equal(alert.source.error_category, "exception");
  assert.equal(JSON.stringify(alert).includes("secret bearer token"), false);
  assert.ok(parseOperationalAlert(alert));
  assert.equal(parseOperationalAlert({ ...alert, token: "forbidden" }), null);
});


test("expected deployment resets do not page as runtime failures", () => {
  const alerts = alertsFromTrace(trace([], {
    outcome: "exception",
    exceptions: [{
      name: "Error",
      message: "Durable Object reset because its code was updated.",
      timestamp: Date.now(),
    }],
  }));

  assert.deepEqual(alerts, []);
});


test("recovered web container capacity alarms do not page", () => {
  const alerts = alertsFromTrace(trace([], {
    event: { scheduledTime: new Date("2026-08-12T02:01:35.752Z") },
    entrypoint: "WebContainer",
    executionModel: "durableObject",
    exceptions: [{
      name: "Error",
      message: "Maximum number of running container instances exceeded. Try again later, or try configuring a higher value for max_instances",
      timestamp: Date.now(),
    }],
  }));

  assert.deepEqual(alerts, []);
});


test("container capacity exceptions outside recovered web alarms remain critical", () => {
  const capacityException = {
    name: "Error",
    message: "Maximum number of running container instances exceeded. Try again later, or try configuring a higher value for max_instances",
    timestamp: Date.now(),
  };
  const [requestAlert] = alertsFromTrace(trace([], {
    entrypoint: "WebContainer",
    executionModel: "durableObject",
    exceptions: [capacityException],
  }));
  const [failedAlarmAlert] = alertsFromTrace(trace([], {
    event: { scheduledTime: new Date("2026-08-12T02:01:35.752Z") },
    entrypoint: "WebContainer",
    executionModel: "durableObject",
    outcome: "exception",
    exceptions: [capacityException],
  }));
  const [mixedAlarmAlert] = alertsFromTrace(trace([], {
    event: { scheduledTime: new Date("2026-08-12T02:01:35.752Z") },
    entrypoint: "WebContainer",
    executionModel: "durableObject",
    exceptions: [
      capacityException,
      { name: "Error", message: "unexpected failure", timestamp: Date.now() },
    ],
  }));

  assert.equal(requestAlert.kind, "worker_runtime_failure");
  assert.equal(requestAlert.severity, "critical");
  assert.equal(requestAlert.source.error_category, "worker_exception");
  assert.equal(failedAlarmAlert.source.error_category, "exception");
  assert.equal(mixedAlarmAlert.source.error_category, "worker_exception");
});


test("dedupe policy leases, commits, expires, and releases claims", () => {
  const first = claimAlert(undefined, 1_000, 10_000, "token-1");
  assert.equal(first.allowed, true);
  assert.equal(claimAlert(first.state, 2_000, 10_000, "token-2").allowed, false);

  const committed = commitAlert(first.state, "token-1", 3_000);
  assert.ok(committed);
  assert.equal(claimAlert(committed, 9_000, 10_000, "token-3").allowed, false);
  assert.equal(claimAlert(committed, 13_001, 10_000, "token-4").allowed, true);

  const pending = claimAlert(undefined, 20_000, 10_000, "token-5");
  const released = releaseAlert(pending.state, "token-5");
  assert.ok(released);
  assert.equal(claimAlert(released, 20_001, 10_000, "token-6").allowed, true);
});


test("tail dispatch enqueues once per fingerprint inside the dedupe window", async () => {
  const messages = [];
  const environment = {
    ALERTS_QUEUE: { send: async (message) => messages.push(message) },
    ALERT_DEDUPLICATOR: new FakeDeduplicatorNamespace(),
    ALERT_DEDUPE_WINDOW_SECONDS: "900",
  };
  const event = trace([{ event: "d1_operation_failure", error_category: "internal" }]);

  await handleTailEvents([event], environment);
  await handleTailEvents([event], environment);

  assert.equal(messages.length, 1);
  assert.equal(messages[0].kind, "d1_failure");
  assert.ok(alertFingerprint(messages[0]).includes("d1_failure"));
});


test("failed queue publication releases the claim for a later delivery", async () => {
  const deduplicator = new FakeDeduplicatorNamespace();
  const event = trace([{ event: "export_failure", error_category: "internal" }]);
  await handleTailEvents([event], {
    ALERTS_QUEUE: { send: async () => { throw new Error("queue down"); } },
    ALERT_DEDUPLICATOR: deduplicator,
  });

  const messages = [];
  await handleTailEvents([event], {
    ALERTS_QUEUE: { send: async (message) => messages.push(message) },
    ALERT_DEDUPLICATOR: deduplicator,
  });

  assert.equal(messages.length, 1);
});
