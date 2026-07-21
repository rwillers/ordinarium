import {
  alertFingerprint,
  alertsFromTrace,
  type OperationalAlertMessage,
} from "./operational_alerts.ts";

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
};

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
