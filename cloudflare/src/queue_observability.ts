import {
  deploymentResources,
  type DeploymentResources,
} from "./deployment_resources.ts";
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
  DEPLOYMENT_ENV: string;
}

type QueuePolicy = {
  resource: keyof Pick<
    DeploymentResources,
    "pcoQueue" | "pcoDlq" | "emailQueue" | "emailDlq"
  >;
  binding: keyof Pick<
    QueueObservabilityEnvironment,
    "PCO_JOBS_QUEUE" | "PCO_JOBS_DLQ" | "EMAIL_JOBS_QUEUE" | "EMAIL_JOBS_DLQ"
  >;
  role: "pco-jobs" | "email-jobs";
  dlq: boolean;
  backlogThreshold: number;
  oldestAgeThresholdSeconds: number;
};

const QUEUE_POLICIES: readonly QueuePolicy[] = [
  {
    resource: "pcoQueue",
    binding: "PCO_JOBS_QUEUE",
    role: "pco-jobs",
    dlq: false,
    backlogThreshold: 25,
    oldestAgeThresholdSeconds: 300,
  },
  {
    resource: "pcoDlq",
    binding: "PCO_JOBS_DLQ",
    role: "pco-jobs",
    dlq: true,
    backlogThreshold: 0,
    oldestAgeThresholdSeconds: 0,
  },
  {
    resource: "emailQueue",
    binding: "EMAIL_JOBS_QUEUE",
    role: "email-jobs",
    dlq: false,
    backlogThreshold: 10,
    oldestAgeThresholdSeconds: 120,
  },
  {
    resource: "emailDlq",
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
  const resources = deploymentResources(environment.DEPLOYMENT_ENV);
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
          queue: resources[policy.resource],
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
          queue: resources[policy.resource],
          container_role: policy.role,
          dlq: policy.dlq,
          error_category: errorCategory(error),
        });
      }
    }),
  );
};
