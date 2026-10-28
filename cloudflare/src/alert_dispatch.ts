import {
  alertFingerprint,
  alertsFromTrace,
  type OperationalAlertMessage,
} from "./operational_alerts.ts";
import { sanitizeIdentifier } from "./telemetry.ts";

interface AlertQueue {
  send(message: OperationalAlertMessage): Promise<unknown>;
}

interface AlertDeduplicatorStub {
  fetch(request: Request): Promise<Response>;
}

interface AlertDeduplicatorNamespace {
  getByName(name: string): AlertDeduplicatorStub;
}

export interface AlertTailEnvironment {
  ALERTS_QUEUE: AlertQueue;
  ALERT_DEDUPLICATOR: AlertDeduplicatorNamespace;
  ALERT_DEDUPE_WINDOW_SECONDS?: string;
}

interface ClaimResponse {
  allowed: boolean;
  token: string | null;
}

export const handleTailEvents = async (
  traces: TraceItem[],
  environment: AlertTailEnvironment,
): Promise<void> => {
  for (const trace of traces) {
    for (const alert of alertsFromTrace(trace)) {
      await enqueueDeduplicatedAlert(alert, environment);
    }
  }
  // Process every directly actionable alert first. Monitoring failures must
  // never prevent a delivery, D1, security, or dead-letter alert from paging.
  const observations = traces.flatMap(queueMetricsObservations)
    .sort((left, right) => left.observed_at - right.observed_at);
  for (const observation of observations) {
    let sustained: boolean;
    let category = "metrics_unavailable";
    try {
      const stub = environment.ALERT_DEDUPLICATOR.getByName(
        `queue-metrics:${observation.trace.scriptName}:${observation.queue}`,
      );
      const response = await stub.fetch(new Request("http://alert-dedupe.internal/metrics", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          healthy: observation.healthy,
          observed_at: observation.observed_at,
        }),
      }));
      if (!response.ok) {
        throw new Error("metrics_monitor_unavailable");
      }
      const result = await response.json() as { sustained?: unknown };
      if (typeof result.sustained !== "boolean") {
        throw new Error("invalid_metrics_monitor_response");
      }
      sustained = result.sustained;
    } catch {
      // Fail closed if durable tracking is unavailable, rather than silently
      // disabling pages for a persistent visibility outage.
      sustained = true;
      category = "metrics_monitor_unavailable";
    }
    if (sustained) {
      const healthTrace: TraceItem = {
        ...observation.trace,
        eventTimestamp: observation.observed_at,
        outcome: "ok",
        exceptions: [],
        logs: [{
          timestamp: observation.observed_at,
          level: "error",
          message: [{
            event: "queue_metrics_unavailable",
            queue: observation.queue,
            container_role: observation.role,
            error_category: category,
          }],
        }],
      };
      for (const alert of alertsFromTrace(healthTrace)) {
        await enqueueDeduplicatedAlert(alert, environment);
      }
    }
  }
};

const queueMetricsObservations = (trace: TraceItem) =>
  trace.logs.flatMap((log) => {
    const messages: unknown[] = Array.isArray(log.message) ? log.message : [log.message];
    return messages.flatMap((value) => {
      if (!value || typeof value !== "object") {
        return [];
      }
      const record = value as Record<string, unknown>;
      if (record.event !== "queue_metrics" && record.event !== "queue_metrics_failure") {
        return [];
      }
      const queue = sanitizeIdentifier(record.queue, "");
      if (!queue || !Number.isFinite(log.timestamp)) {
        return [];
      }
      return [{
        trace,
        queue,
        role: sanitizeIdentifier(record.container_role),
        healthy: record.event === "queue_metrics",
        observed_at: log.timestamp,
      }];
    });
  });

const enqueueDeduplicatedAlert = async (
  alert: OperationalAlertMessage,
  environment: AlertTailEnvironment,
): Promise<void> => {
  const stub = environment.ALERT_DEDUPLICATOR.getByName(alertFingerprint(alert));
  const token = crypto.randomUUID();
  const now = Date.now();
  const windowMs = dedupeWindowMs(environment.ALERT_DEDUPE_WINDOW_SECONDS);
  const claim = await callDeduplicator(stub, "claim", { token, now, window_ms: windowMs });
  if (!claim.allowed || !claim.token) {
    return;
  }
  try {
    await environment.ALERTS_QUEUE.send(alert);
    await callDeduplicator(stub, "commit", {
      token: claim.token,
      now: Date.now(),
      window_ms: windowMs,
    });
  } catch {
    await callDeduplicator(stub, "release", {
      token: claim.token,
      now: Date.now(),
      window_ms: windowMs,
    }).catch(() => undefined);
    console.error({ event: "alert_enqueue_failure", error_category: "internal" });
  }
};

interface DedupeOperation {
  token: string;
  now: number;
  window_ms: number;
}

const callDeduplicator = async (
  stub: AlertDeduplicatorStub,
  operation: "claim" | "commit" | "release",
  payload: DedupeOperation,
): Promise<ClaimResponse> => {
  const response = await stub.fetch(
    new Request(`http://alert-dedupe.internal/${operation}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
  if (!response.ok) {
    throw new Error("alert_deduplicator_unavailable");
  }
  return (await response.json()) as ClaimResponse;
};

const dedupeWindowMs = (configured: string | undefined): number => {
  const seconds = Number.parseInt(configured || "900", 10);
  if (!Number.isFinite(seconds) || seconds < 60 || seconds > 86_400) {
    return 900_000;
  }
  return seconds * 1000;
};
