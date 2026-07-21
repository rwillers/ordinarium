import { emitTelemetry, errorCategory } from "./telemetry.ts";

interface MetricsQueue {
  metrics(): Promise<{
    backlogCount: number;
    backlogBytes: number;
    oldestMessageTimestamp?: Date;
  }>;
}

export interface QueueObservabilityEnvironment {
  PCO_JOBS_QUEUE: MetricsQueue;
  PCO_JOBS_DLQ: MetricsQueue;
  EMAIL_JOBS_QUEUE: MetricsQueue;
  EMAIL_JOBS_DLQ: MetricsQueue;
}

type QueuePolicy = {
  name: string;
  binding: keyof QueueObservabilityEnvironment;
  role: "pco-jobs" | "email-jobs";
  dlq: boolean;
  backlogThreshold: number;
  oldestAgeThresholdSeconds: number;
};

const QUEUE_POLICIES: readonly QueuePolicy[] = [
  {
    name: "ordinarium-app-staging-pco-jobs",
    binding: "PCO_JOBS_QUEUE",
    role: "pco-jobs",
    dlq: false,
    backlogThreshold: 25,
    oldestAgeThresholdSeconds: 300,
  },
  {
    name: "ordinarium-app-staging-pco-jobs-dlq",
    binding: "PCO_JOBS_DLQ",
    role: "pco-jobs",
    dlq: true,
    backlogThreshold: 0,
    oldestAgeThresholdSeconds: 0,
  },
  {
    name: "ordinarium-app-staging-email-jobs",
    binding: "EMAIL_JOBS_QUEUE",
    role: "email-jobs",
    dlq: false,
    backlogThreshold: 10,
    oldestAgeThresholdSeconds: 120,
  },
  {
    name: "ordinarium-app-staging-email-jobs-dlq",
    binding: "EMAIL_JOBS_DLQ",
    role: "email-jobs",
    dlq: true,
    backlogThreshold: 0,
    oldestAgeThresholdSeconds: 0,
  },
];

export const emitQueueMetrics = async (
  environment: QueueObservabilityEnvironment,
  now = Date.now(),
): Promise<void> => {
  await Promise.all(
    QUEUE_POLICIES.map(async (policy) => {
      try {
        const metrics = await environment[policy.binding].metrics();
        const oldestAgeSeconds = metrics.oldestMessageTimestamp
          ? Math.max(
              0,
              Math.floor((now - metrics.oldestMessageTimestamp.getTime()) / 1000),
            )
          : 0;
        const thresholdExceeded = policy.dlq
          ? metrics.backlogCount > 0
          : metrics.backlogCount > policy.backlogThreshold ||
            oldestAgeSeconds > policy.oldestAgeThresholdSeconds;
        emitTelemetry(thresholdExceeded ? "error" : "info", "queue_metrics", {
          queue: policy.name,
          container_role: policy.role,
          backlog_count: metrics.backlogCount,
          backlog_bytes: metrics.backlogBytes,
          oldest_age_seconds: oldestAgeSeconds,
          dlq: policy.dlq,
          threshold_exceeded: thresholdExceeded,
          error_category: thresholdExceeded
            ? policy.dlq
              ? "dead_letter"
              : "queue_backlog"
            : undefined,
        });
      } catch (error: unknown) {
        emitTelemetry("error", "queue_metrics_failure", {
          queue: policy.name,
          container_role: policy.role,
          dlq: policy.dlq,
          error_category: errorCategory(error),
        });
      }
    }),
  );
};
