import { sanitizeIdentifier, sanitizeRoute } from "./telemetry.ts";

export const ALERT_QUEUE_NAME = "ordinarium-app-staging-alerts";
export const ALERT_DLQ_NAME = `${ALERT_QUEUE_NAME}-dlq`;

export const ALERT_KINDS = [
  "worker_runtime_failure",
  "worker_request_failure",
  "container_started",
  "container_failure",
  "d1_failure",
  "queue_failure",
  "queue_backlog",
  "dead_letter",
  "export_failure",
  "pco_authorization_failure",
  "edge_security_failure",
] as const;

export type AlertKind = (typeof ALERT_KINDS)[number];
export type AlertSeverity = "warning" | "critical";

export interface AlertSource {
  script_name: string;
  container_role: string | null;
  queue: string | null;
  route: string | null;
  status: number | null;
  error_category: string | null;
  request_id: string | null;
  job_id: string | null;
}

export interface OperationalAlertMessage {
  alert_id: string;
  kind: AlertKind;
  severity: AlertSeverity;
  occurred_at: string;
  source: AlertSource;
}

type TelemetryRecord = Record<string, unknown>;

const FAILURE_OUTCOMES = new Set([
  "exception",
  "exceededCpu",
  "exceededMemory",
  "scriptNotFound",
]);

const DEPLOYMENT_RESET_MESSAGE =
  "Durable Object reset because its code was updated.";

export const alertsFromTrace = (trace: TraceItem): OperationalAlertMessage[] => {
  const occurredAt = new Date(trace.eventTimestamp ?? Date.now()).toISOString();
  const scriptName = sanitizeIdentifier(trace.scriptName, "unknown-script");
  const alerts: OperationalAlertMessage[] = [];

  if (
    (FAILURE_OUTCOMES.has(trace.outcome) || trace.exceptions.length > 0) &&
    !isExpectedDeploymentReset(trace)
  ) {
    alerts.push(
      createAlert("worker_runtime_failure", "critical", occurredAt, scriptName, {
        error_category: sanitizeIdentifier(trace.outcome, "worker_exception"),
      }),
    );
  }

  for (const log of trace.logs) {
    for (const record of telemetryRecords(log.message)) {
      const alert = alertFromTelemetry(record, occurredAt, scriptName);
      if (alert) {
        alerts.push(alert);
      }
    }
  }

  return deduplicateWithinTrace(alerts);
};

const isExpectedDeploymentReset = (trace: TraceItem): boolean =>
  trace.outcome === "exception" &&
  trace.exceptions.length > 0 &&
  trace.exceptions.every(
    (exception) => exception.message === DEPLOYMENT_RESET_MESSAGE,
  );

export const parseOperationalAlert = (
  value: unknown,
): OperationalAlertMessage | null => {
  if (!hasExactKeys(value, ["alert_id", "kind", "severity", "occurred_at", "source"])) {
    return null;
  }
  if (
    !isIdentifier(value.alert_id) ||
    !ALERT_KINDS.includes(value.kind as AlertKind) ||
    (value.severity !== "warning" && value.severity !== "critical") ||
    !isIsoTimestamp(value.occurred_at) ||
    !isAlertSource(value.source)
  ) {
    return null;
  }
  return {
    alert_id: value.alert_id,
    kind: value.kind as AlertKind,
    severity: value.severity,
    occurred_at: value.occurred_at,
    source: value.source,
  };
};

export const alertFingerprint = (alert: OperationalAlertMessage): string =>
  [
    alert.kind,
    alert.source.container_role,
    alert.source.queue,
    alert.source.route,
    alert.source.status,
    alert.source.error_category,
  ]
    .map((value) => value ?? "-")
    .join("|");

const alertFromTelemetry = (
  record: TelemetryRecord,
  occurredAt: string,
  scriptName: string,
): OperationalAlertMessage | null => {
  const event = sanitizeIdentifier(record.event, "unknown");
  if (event === "container_started") {
    return createAlert("container_started", "warning", occurredAt, scriptName, record);
  }
  if (event === "container_stopped" && record.error_category) {
    return createAlert("container_failure", "critical", occurredAt, scriptName, record);
  }
  if (event === "worker_request_failure") {
    return createAlert("worker_request_failure", "critical", occurredAt, scriptName, record);
  }
  if (event === "d1_operation_failure") {
    return createAlert("d1_failure", "critical", occurredAt, scriptName, record);
  }
  if (event === "export_failure") {
    return createAlert("export_failure", "critical", occurredAt, scriptName, record);
  }
  if (event === "pco_auth_failure") {
    return createAlert(
      "pco_authorization_failure",
      "critical",
      occurredAt,
      scriptName,
      record,
    );
  }
  if (event === "edge_rate_limit_failure") {
    return createAlert("edge_security_failure", "critical", occurredAt, scriptName, record);
  }
  if (
    event === "queue_delivery_failure" ||
    event === "queue_publication_failure" ||
    event === "queue_metrics_failure"
  ) {
    return createAlert("queue_failure", "critical", occurredAt, scriptName, record);
  }
  if (event !== "queue_metrics" || record.threshold_exceeded !== true) {
    return null;
  }
  return createAlert(
    record.dlq === true ? "dead_letter" : "queue_backlog",
    record.dlq === true ? "critical" : "warning",
    occurredAt,
    scriptName,
    record,
  );
};

const createAlert = (
  kind: AlertKind,
  severity: AlertSeverity,
  occurredAt: string,
  scriptName: string,
  record: TelemetryRecord,
): OperationalAlertMessage => ({
  alert_id: crypto.randomUUID(),
  kind,
  severity,
  occurred_at: occurredAt,
  source: {
    script_name: scriptName,
    container_role: optionalIdentifier(record.container_role),
    queue: optionalIdentifier(record.queue),
    route:
      typeof record.route === "string" ? sanitizeRoute(record.route) : null,
    status: validStatus(record.status),
    error_category: optionalIdentifier(record.error_category),
    request_id: optionalIdentifier(record.request_id),
    job_id: optionalIdentifier(record.job_id),
  },
});

const telemetryRecords = (message: unknown): TelemetryRecord[] => {
  const values = Array.isArray(message) ? message : [message];
  return values.filter(
    (value): value is TelemetryRecord =>
      Boolean(value) && typeof value === "object" && !Array.isArray(value),
  );
};

const deduplicateWithinTrace = (
  alerts: OperationalAlertMessage[],
): OperationalAlertMessage[] => {
  const fingerprints = new Set<string>();
  return alerts.filter((alert) => {
    const fingerprint = alertFingerprint(alert);
    if (fingerprints.has(fingerprint)) {
      return false;
    }
    fingerprints.add(fingerprint);
    return true;
  });
};

const isAlertSource = (value: unknown): value is AlertSource => {
  if (
    !hasExactKeys(value, [
      "script_name",
      "container_role",
      "queue",
      "route",
      "status",
      "error_category",
      "request_id",
      "job_id",
    ]) ||
    !isIdentifier(value.script_name)
  ) {
    return false;
  }
  return (
    isOptionalIdentifier(value.container_role) &&
    isOptionalIdentifier(value.queue) &&
    (value.route === null || (typeof value.route === "string" && value.route.length <= 256)) &&
    (value.status === null || validStatus(value.status) !== null) &&
    isOptionalIdentifier(value.error_category) &&
    isOptionalIdentifier(value.request_id) &&
    isOptionalIdentifier(value.job_id)
  );
};

const hasExactKeys = <K extends string>(
  value: unknown,
  expectedKeys: readonly K[],
): value is Record<K, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const keys = Object.keys(value);
  return keys.length === expectedKeys.length && expectedKeys.every((key) => Object.hasOwn(value, key));
};

const isIdentifier = (value: unknown): value is string =>
  typeof value === "string" && /^[A-Za-z0-9._:@+-]{1,128}$/.test(value);

const optionalIdentifier = (value: unknown): string | null =>
  value === null || value === undefined ? null : sanitizeIdentifier(value, "unknown");

const isOptionalIdentifier = (value: unknown): value is string | null =>
  value === null || isIdentifier(value);

const validStatus = (value: unknown): number | null =>
  typeof value === "number" && Number.isInteger(value) && value >= 100 && value <= 599
    ? value
    : null;

const isIsoTimestamp = (value: unknown): value is string =>
  typeof value === "string" &&
  value.length <= 32 &&
  Number.isFinite(Date.parse(value));
