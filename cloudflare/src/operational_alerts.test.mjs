import assert from "node:assert/strict";
import test from "node:test";

import { handleTailEvents } from "./alert_dispatch.ts";
import { claimAlert, commitAlert, releaseAlert } from "./alert_dedupe_policy.ts";
import { observeQueueMetrics } from "./queue_metrics_health.ts";
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
        if (operation === "metrics") {
          const result = observeQueueMetrics(state, payload);
          this.states.set(name, result.state);
          return Response.json({ sustained: result.sustained });
        }
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


test("tail classification covers active paging categories", () => {
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
    "dead_letter",
    "export_failure",
    "pco_authorization_failure",
    "edge_security_failure",
    "turnstile_failure",
  ]);
});


test("primary queue backlog remains telemetry and does not enqueue warnings", () => {
  assert.deepEqual(
    alertsFromTrace(trace([{
      event: "queue_metrics",
      queue: "pco",
      threshold_exceeded: true,
      dlq: false,
    }])),
    [],
  );
});


test("routine container starts remain telemetry and do not enqueue alerts", () => {
  assert.deepEqual(
    alertsFromTrace(trace([{ event: "container_started", container_role: "web" }])),
    [],
  );
});


test("rejected edge probes remain telemetry and do not enqueue alerts", () => {
  assert.deepEqual(
    alertsFromTrace(trace([{
      event: "edge_probe_rejected",
      route: "/assets/file-uploader/server/php/index.php",
      status: 404,
      error_category: "foreign_server_extension",
    }])),
    [],
  );
});


test("runtime failures are sanitized and raw exception text never crosses the queue", () => {
  const exceptionTimestamp = Date.parse("2026-07-21T12:00:43Z");
  const [alert] = alertsFromTrace(trace([], {
    outcome: "exception",
    exceptions: [{ name: "Error", message: "secret bearer token", timestamp: exceptionTimestamp }],
  }));

  assert.equal(alert.kind, "worker_runtime_failure");
  assert.equal(alert.occurred_at, "2026-07-21T12:00:43.000Z");
  assert.equal(alert.source.error_category, "exception");
  assert.equal(JSON.stringify(alert).includes("secret bearer token"), false);
  assert.ok(parseOperationalAlert(alert));
  assert.equal(parseOperationalAlert({ ...alert, token: "forbidden" }), null);
});


test("D1 runtime exceptions use the D1 fingerprint without exposing the exception", () => {
  const exceptionTimestamp = Date.parse("2026-08-12T19:22:12.299Z");
  const [alert] = alertsFromTrace(trace([], {
    outcome: "exception",
    exceptions: [{
      name: "Error",
      message: "D1_ERROR: D1 DB storage operation exceeded timeout which caused object to be reset.",
      timestamp: exceptionTimestamp,
    }],
  }));

  assert.equal(alert.kind, "d1_failure");
  assert.equal(alert.occurred_at, "2026-08-12T19:22:12.299Z");
  assert.equal(alert.source.container_role, "d1-bridge");
  assert.equal(alert.source.error_category, "internal");
  assert.equal(JSON.stringify(alert).includes("storage operation"), false);
});


test("scheduled D1 runtime exceptions use the reconciliation role", () => {
  const exceptionTimestamp = Date.parse("2026-08-23T12:31:02.276Z");
  const [alert] = alertsFromTrace(trace([], {
    event: {
      cron: "* * * * *",
      scheduledTime: Date.parse("2026-08-23T12:30:50Z"),
    },
    outcome: "exception",
    exceptions: [{
      name: "Error",
      message: "D1_ERROR: Network connection lost.",
      timestamp: exceptionTimestamp,
    }],
  }));

  assert.equal(alert.kind, "d1_failure");
  assert.equal(alert.occurred_at, "2026-08-23T12:31:02.276Z");
  assert.equal(alert.source.container_role, "d1-reconciliation");
  assert.equal(alert.source.error_category, "internal");
  assert.equal(JSON.stringify(alert).includes("Network connection lost"), false);
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


test("canceled web readiness streams remain telemetry and do not page", () => {
  const alerts = alertsFromTrace(trace([], {
    event: { rpcMethod: "fetchWithReadiness" },
    entrypoint: "WebContainer",
    executionModel: "durableObject",
    outcome: "canceled",
    exceptions: [{
      name: "Error",
      message: "ReadableStream received over RPC disconnected prematurely.",
      timestamp: Date.now(),
    }],
  }));

  assert.deepEqual(alerts, []);
});


test("premature RPC stream errors outside canceled readiness calls remain critical", () => {
  const [alert] = alertsFromTrace(trace([], {
    event: { rpcMethod: "otherMethod" },
    entrypoint: "WebContainer",
    executionModel: "durableObject",
    outcome: "exception",
    exceptions: [{
      name: "Error",
      message: "ReadableStream received over RPC disconnected prematurely.",
      timestamp: Date.now(),
    }],
  }));

  assert.equal(alert.kind, "worker_runtime_failure");
  assert.equal(alert.severity, "critical");
});


test("known web container lifecycle storage alarms remain telemetry only", () => {
  const commonOptions = {
    event: { scheduledTime: new Date("2026-08-12T14:45:14.082Z") },
    entrypoint: "WebContainer",
    executionModel: "durableObject",
    outcome: "exception",
  };
  const monitorStorageFailure = {
    name: "Error",
    message: "internal error; reference = 0947fnii4v34h0t0sl67p7bf",
    timestamp: Date.parse("2026-08-12T14:48:57.533Z"),
    stack: "Error: internal error\n    at async ContainerState.update (index.js:184:9)\n    at async ContainerState.setStopped (index.js:151:9)",
  };
  const durableStorageReset = {
    name: "Error",
    message: "Internal error in Durable Object storage caused object to be reset; reference = abc123",
    timestamp: Date.parse("2026-08-12T15:00:00Z"),
    stack: "Error: storage reset\n    at async ContainerState.update (index.js:184:9)",
  };

  assert.deepEqual(
    alertsFromTrace(trace([], {
      ...commonOptions,
      exceptions: [monitorStorageFailure],
    })),
    [],
  );
  assert.deepEqual(
    alertsFromTrace(trace([], {
      ...commonOptions,
      exceptions: [durableStorageReset],
    })),
    [],
  );
});


test("internal references outside known web lifecycle alarms remain critical", () => {
  const exception = {
    name: "Error",
    message: "internal error; reference = abc123",
    timestamp: Date.parse("2026-08-12T15:00:00Z"),
    stack: "Error: internal error\n    at applicationHandler (src/index.ts:10:2)",
  };
  const alarm = { scheduledTime: new Date("2026-08-12T14:45:14.082Z") };

  const [unknownStackAlert] = alertsFromTrace(trace([], {
    event: alarm,
    entrypoint: "WebContainer",
    executionModel: "durableObject",
    outcome: "exception",
    exceptions: [exception],
  }));
  const [requestAlert] = alertsFromTrace(trace([], {
    entrypoint: "WebContainer",
    executionModel: "durableObject",
    outcome: "exception",
    exceptions: [{
      ...exception,
      stack: "Error: internal error\n    at async ContainerState.update (index.js:184:9)",
    }],
  }));

  assert.equal(unknownStackAlert.kind, "worker_runtime_failure");
  assert.equal(requestAlert.kind, "worker_runtime_failure");
});


test("inactive web container lifecycle alarms remain telemetry only", () => {
  const alerts = alertsFromTrace(trace([], {
    event: { scheduledTime: new Date("2026-08-21T19:15:00.000Z") },
    entrypoint: "WebContainer",
    executionModel: "durableObject",
    outcome: "exception",
    exceptions: [{
      name: "Error",
      message: "Connection closed: this Durable Object instance is no longer active. Reconnect or retry the request.",
      timestamp: Date.parse("2026-08-21T19:15:00.000Z"),
      stack: "Error: Connection closed\n    at ContainerState.update (index.js:184:24)\n    at ContainerState.setStatusAndupdate (index.js:179:16)\n    at ContainerState.setStopped (index.js:150:16)",
    }],
  }));

  assert.deepEqual(alerts, []);
});


test("inactive connection errors outside exact lifecycle alarms remain critical", () => {
  const message = "Connection closed: this Durable Object instance is no longer active. Reconnect or retry the request.";
  const lifecycleStack = "Error: Connection closed\n    at ContainerState.update (index.js:184:24)\n    at ContainerState.setStatusAndupdate (index.js:179:16)\n    at ContainerState.setStopped (index.js:150:16)";
  const alarm = { scheduledTime: new Date("2026-08-21T19:15:00.000Z") };
  const cases = [
    { event: null, entrypoint: "WebContainer", executionModel: "durableObject", stack: lifecycleStack },
    { event: alarm, entrypoint: "OtherContainer", executionModel: "durableObject", stack: lifecycleStack },
    { event: alarm, entrypoint: "WebContainer", executionModel: "stateless", stack: lifecycleStack },
    { event: alarm, entrypoint: "WebContainer", executionModel: "durableObject", stack: "Error: Connection closed\n    at applicationHandler (src/index.ts:10:2)" },
  ];

  for (const options of cases) {
    const [alert] = alertsFromTrace(trace([], {
      ...options,
      outcome: "exception",
      exceptions: [{
        name: "Error",
        message,
        timestamp: Date.parse("2026-08-21T19:15:00.000Z"),
        stack: options.stack,
      }],
    }));
    assert.equal(alert.kind, "worker_runtime_failure");
    assert.equal(alert.severity, "critical");
  }
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


test("D1 telemetry and a related runtime exception deduplicate across traces", async () => {
  const messages = [];
  const environment = {
    ALERTS_QUEUE: { send: async (message) => messages.push(message) },
    ALERT_DEDUPLICATOR: new FakeDeduplicatorNamespace(),
    ALERT_DEDUPE_WINDOW_SECONDS: "900",
  };
  const telemetry = trace([{
    event: "d1_operation_failure",
    container_role: "d1-bridge",
    error_category: "internal",
  }]);
  const runtime = trace([], {
    outcome: "exception",
    exceptions: [{
      name: "Error",
      message: "D1_ERROR: D1 DB storage operation exceeded timeout which caused object to be reset.",
      timestamp: Date.now(),
    }],
  });

  await handleTailEvents([telemetry], environment);
  await handleTailEvents([runtime], environment);

  assert.equal(messages.length, 1);
  assert.equal(messages[0].kind, "d1_failure");
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

const octoberAlarm = (exceptions, overrides = {}) => trace([], {
  event: { scheduledTime: new Date("2026-10-27T22:38:23Z") },
  entrypoint: "WebContainer", executionModel: "durableObject", outcome: "exception",
  exceptions: exceptions.map((exception) => ({
    name: "Error", timestamp: Date.parse("2026-10-27T22:41:23.852Z"), ...exception,
  })),
  ...overrides,
});
const inactiveMessage = "Connection closed: this Durable Object instance is no longer active. Reconnect or retry the request.";
const alarmOnlyStack = "    at WebContainer.alarm (index.js:1407:28)";
const resetMessage = "Internal error in Durable Object storage caused object to be reset; reference = a7brfpocabv4v194opmh5hjm";

test("October alarm signatures with shortened or omitted platform stacks remain telemetry", () => {
  for (const exception of [
    { message: inactiveMessage, stack: alarmOnlyStack },
    { message: "internal error; reference = 73u8rabpsnbnn3cs7ncsuhei", stack: alarmOnlyStack },
    { message: resetMessage }, { message: resetMessage, stack: alarmOnlyStack },
  ]) {
    assert.deepEqual(alertsFromTrace(octoberAlarm([exception])), []);
  }
  assert.deepEqual(alertsFromTrace(octoberAlarm([
    { message: resetMessage }, { message: resetMessage, stack: alarmOnlyStack },
  ])), []);
});

test("October exceptions outside exact WebContainer alarms still page", () => {
  const exception = { message: inactiveMessage, stack: alarmOnlyStack };
  for (const overrides of [
    { event: null }, { event: { cron: "* * * * *", scheduledTime: Date.now() } },
    { event: { rpcMethod: "fetchWithReadiness" } }, { entrypoint: "PcoJobsContainer" },
    { executionModel: "stateless" }, { outcome: "exceededCpu" }, { outcome: "exceededMemory" },
  ]) {
    assert.equal(alertsFromTrace(octoberAlarm([exception], overrides))[0].severity, "critical");
    assert.equal(alertsFromTrace(octoberAlarm([{ message: resetMessage }], overrides))[0].severity, "critical");
  }
  for (const unsafe of [
    { message: inactiveMessage }, { message: "internal error; reference = abc123" },
    { message: "unrecognized platform error", stack: alarmOnlyStack },
    { message: inactiveMessage + " additional context", stack: alarmOnlyStack },
    { message: inactiveMessage, stack: "    at WebContainer.alarm (application.ts:1:2)" },
    { message: inactiveMessage, stack: alarmOnlyStack + "\n    at applicationHandler (index.js:1:2)" },
    { message: resetMessage, stack: "    at applicationHandler (index.js:1:2)" },
  ]) {
    assert.equal(alertsFromTrace(octoberAlarm([unsafe]))[0].severity, "critical");
  }
  assert.equal(alertsFromTrace(octoberAlarm([
    exception, { message: "unexpected application failure" },
  ]))[0].kind, "worker_runtime_failure");
});

test("suppressing a platform alarm preserves actionable telemetry on the same trace", () => {
  const event = octoberAlarm([{ message: inactiveMessage, stack: alarmOnlyStack }]);
  event.logs = trace([{ event: "worker_request_failure", route: "/services", status: 503 }]).logs;
  assert.deepEqual(alertsFromTrace(event).map((alert) => alert.kind), ["worker_request_failure"]);
});

const metricTrace = (at, healthy = false, queue = "email-dlq", script = "ordinarium-app-production") => {
  const event = trace([{
    event: healthy ? "queue_metrics" : "queue_metrics_failure", queue,
    container_role: "email-jobs", error_category: healthy ? undefined : "internal",
    threshold_exceeded: false,
  }]);
  event.scriptName = script;
  event.logs[0].timestamp = at;
  return event;
};
const metricsEnvironment = () => {
  const messages = [];
  return { messages, environment: {
    ALERTS_QUEUE: { send: async (message) => messages.push(message) },
    ALERT_DEDUPLICATOR: new FakeDeduplicatorNamespace(),
  } };
};

test("a metrics failure followed by recovery never enqueues an alert", async () => {
  const { messages, environment } = metricsEnvironment();
  await handleTailEvents([metricTrace(0), metricTrace(60_000, true), metricTrace(120_000)], environment);
  assert.deepEqual(messages, []);
});

test("durable metrics streaks span Tail calls, sort a batch, and deduplicate pages", async () => {
  const { messages, environment } = metricsEnvironment();
  await handleTailEvents([metricTrace(0)], environment);
  await handleTailEvents([metricTrace(120_000), metricTrace(60_000)], environment);
  await handleTailEvents([metricTrace(180_000)], environment);
  assert.equal(messages.length, 1);
  assert.equal(messages[0].kind, "queue_failure");
  assert.equal(messages[0].occurred_at, "1970-01-01T00:02:00.000Z");
  assert.equal(messages[0].source.error_category, "metrics_unavailable");
  assert.ok(parseOperationalAlert(messages[0]));
});

test("metrics streaks are isolated by queue and deployment script", async () => {
  const { messages, environment } = metricsEnvironment();
  await handleTailEvents([
    metricTrace(0), metricTrace(60_000, false, "pco-dlq"),
    metricTrace(120_000, false, "email-dlq", "ordinarium-app-staging"),
  ], environment);
  assert.deepEqual(messages, []);
});

test("metrics gating cannot suppress delivery failures or nonempty dead letters", async () => {
  const { messages, environment } = metricsEnvironment();
  const event = metricTrace(0);
  event.logs.push(...trace([
    { event: "queue_delivery_failure", queue: "email-dlq", error_category: "internal" },
    { event: "queue_metrics", queue: "pco-dlq", dlq: true, threshold_exceeded: true },
  ]).logs);
  await handleTailEvents([event], environment);
  assert.deepEqual(messages.map((message) => message.kind), ["queue_failure", "dead_letter"]);
});

test("unavailable durable metrics tracking fails closed while preserving other pages", async () => {
  const { messages, environment } = metricsEnvironment();
  const original = environment.ALERT_DEDUPLICATOR.getByName.bind(environment.ALERT_DEDUPLICATOR);
  environment.ALERT_DEDUPLICATOR.getByName = (name) => name.startsWith("queue-metrics:")
    ? { fetch: async () => new Response("unavailable", { status: 503 }) } : original(name);
  await handleTailEvents([
    metricTrace(0), trace([{ event: "d1_operation_failure", error_category: "internal" }]),
  ], environment);
  assert.deepEqual(messages.map((message) => message.kind), ["d1_failure", "queue_failure"]);
  assert.equal(messages[1].source.error_category, "metrics_monitor_unavailable");
});

test("a duplicate sustained metrics observation retries failed publication", async () => {
  const { messages, environment } = metricsEnvironment();
  const send = environment.ALERTS_QUEUE.send;
  environment.ALERTS_QUEUE.send = async () => { throw new Error("queue down"); };
  await handleTailEvents([metricTrace(0), metricTrace(60_000), metricTrace(120_000)], environment);
  environment.ALERTS_QUEUE.send = send;
  await handleTailEvents([metricTrace(120_000)], environment);
  assert.equal(messages.length, 1);
});


test("only monitored metrics unavailability pages directly, and malformed monitor responses fail closed", async () => {
  assert.deepEqual(alertsFromTrace(metricTrace(0)), []);
  const [alert] = alertsFromTrace(trace([{
    event: "queue_metrics_unavailable", queue: "email-dlq", error_category: "metrics_unavailable",
  }]));
  assert.equal(alert.kind, "queue_failure");
  const { messages, environment } = metricsEnvironment();
  const original = environment.ALERT_DEDUPLICATOR.getByName.bind(environment.ALERT_DEDUPLICATOR);
  environment.ALERT_DEDUPLICATOR.getByName = (name) => name.startsWith("queue-metrics:")
    ? { fetch: async () => Response.json({ sustained: "false" }) } : original(name);
  await handleTailEvents([metricTrace(0)], environment);
  assert.equal(messages[0].source.error_category, "metrics_monitor_unavailable");
});
