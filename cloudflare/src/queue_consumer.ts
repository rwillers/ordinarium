import { parseEmailMessage, parsePcoRowMessage } from "./queue_publisher.ts";
import {
  deploymentResources,
  type DeploymentResources,
} from "./deployment_resources.ts";
import { parseOperationalAlert } from "./operational_alerts.ts";
import {
  createRequestId,
  emitTelemetry,
  errorCategory,
  REQUEST_ID_HEADER,
  sanitizeIdentifier,
} from "./telemetry.ts";

const JOB_AUTH_HEADER = "X-Ordinarium-Job-Auth";
const JOB_REQUEST_TIMEOUT_MS = 115_000;
const MAX_RETRY_DELAY_SECONDS = 86_400;

interface JobContainerStub {
  fetch(request: Request): Promise<Response>;
}

interface JobContainerNamespace {
  getByName(name: string): JobContainerStub;
}

export interface QueueConsumerEnvironment {
  PCO_JOBS_CONTAINER: JobContainerNamespace;
  EMAIL_JOBS_CONTAINER: JobContainerNamespace;
  PCO_JOB_SERVICE_AUTH_TOKEN?: string;
  EMAIL_JOB_SERVICE_AUTH_TOKEN?: string;
  DEPLOYMENT_ENV: string;
}

interface QueueMessageLike {
  body: unknown;
  id?: string;
  attempts?: number;
  ack(): void;
  retry(options?: { delaySeconds?: number }): void;
}

interface QueueBatchLike {
  queue: string;
  messages: readonly QueueMessageLike[];
}

interface ConsumerRoute {
  parse: (body: unknown) => object | null;
  namespace: JobContainerNamespace;
  instanceName: (jobId: string) => string;
  path: string;
  authToken?: string;
  queueName: string;
  role: "pco-jobs" | "email-jobs";
  dlq: boolean;
}

export const handleQueueBatch = async (
  batch: QueueBatchLike,
  environment: QueueConsumerEnvironment,
): Promise<void> => {
  const route = routeForQueue(
    batch.queue,
    environment,
    deploymentResources(environment.DEPLOYMENT_ENV),
  );
  if (!route) {
    emitTelemetry("error", "queue_unknown_batch", {
      queue: sanitizeIdentifier(batch.queue),
      error_category: "unknown_queue",
    });
    for (const message of batch.messages) {
      message.retry();
    }
    return;
  }

  for (const message of batch.messages) {
    const payload = route.parse(message.body);
    if (!payload) {
      emitTelemetry("error", "queue_message_discarded", {
        queue: route.queueName,
        container_role: route.role,
        dlq: route.dlq,
        error_category: "invalid_message",
      });
      message.ack();
      continue;
    }
    await deliverMessage(message, payload, route);
  }
};

const deliverMessage = async (
  message: QueueMessageLike,
  payload: object,
  route: ConsumerRoute,
): Promise<void> => {
  const requestId = createRequestId();
  const jobId = payloadIdentifier(payload);
  if (!route.authToken) {
    emitTelemetry("error", "queue_delivery_failure", {
      request_id: requestId,
      queue: route.queueName,
      container_role: route.role,
      job_id: jobId,
      dlq: route.dlq,
      error_category: "configuration",
    });
    message.retry();
    return;
  }

  const request = new Request(`http://jobs.internal${route.path}`, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "content-type": "application/json",
      [JOB_AUTH_HEADER]: route.authToken,
      [REQUEST_ID_HEADER]: requestId,
    },
    signal: AbortSignal.timeout(JOB_REQUEST_TIMEOUT_MS),
  });

  let response: Response;
  try {
    response = await route.namespace
      .getByName(route.instanceName(jobId))
      .fetch(request);
  } catch (error: unknown) {
    emitTelemetry("error", "queue_delivery_failure", {
      request_id: requestId,
      queue: route.queueName,
      container_role: route.role,
      job_id: jobId,
      dlq: route.dlq,
      error_category: errorCategory(error),
    });
    message.retry();
    return;
  }

  const disposition = await readJobDisposition(response);
  if (disposition.terminal) {
    const isPcoAuthFailure =
      route.role === "pco-jobs" && disposition.reason === "auth";
    emitTelemetry(
      isPcoAuthFailure || route.dlq ? "error" : "info",
      isPcoAuthFailure ? "pco_auth_failure" : "queue_job_terminal",
      {
        request_id: requestId,
        queue: route.queueName,
        container_role: route.role,
        job_id: jobId,
        dlq: route.dlq,
        disposition: disposition.reason,
        error_category: isPcoAuthFailure
          ? "pco_auth"
          : route.dlq
            ? "dead_letter"
            : undefined,
      },
    );
    message.ack();
    return;
  }
  const delaySeconds = await retryDelaySeconds(response);
  emitTelemetry("warn", "queue_job_retry", {
    request_id: requestId,
    queue: route.queueName,
    container_role: route.role,
    job_id: jobId,
    dlq: route.dlq,
    status: response.status,
    retry_delay_seconds: delaySeconds,
    error_category: sanitizeIdentifier(disposition.reason, "job_unavailable"),
  });
  message.retry(delaySeconds === undefined ? undefined : { delaySeconds });
};

const routeForQueue = (
  queueName: string,
  environment: QueueConsumerEnvironment,
  resources: DeploymentResources,
): ConsumerRoute | null => {
  if (queueName === resources.pcoQueue || queueName === resources.pcoDlq) {
    // DLQ retries are finite even at the platform maximum. A later scheduled D1
    // reconciliation pass must terminalize stale records after a prolonged
    // container or D1 outage; queue delivery alone cannot guarantee that state.
    return {
      parse: parsePcoRowMessage,
      namespace: environment.PCO_JOBS_CONTAINER,
      instanceName: () => resources.pcoJobsInstance,
      path:
        queueName === resources.pcoQueue
          ? "/jobs/pco/rows/process"
          : "/jobs/pco/rows/dead-letter",
      authToken: environment.PCO_JOB_SERVICE_AUTH_TOKEN,
      queueName,
      role: "pco-jobs",
      dlq: queueName === resources.pcoDlq,
    };
  }
  if (queueName === resources.emailQueue || queueName === resources.emailDlq) {
    return {
      parse: parseEmailMessage,
      namespace: environment.EMAIL_JOBS_CONTAINER,
      instanceName: resources.emailJobsInstance,
      path:
        queueName === resources.emailQueue
          ? "/jobs/email/resets/process"
          : "/jobs/email/resets/dead-letter",
      authToken: environment.EMAIL_JOB_SERVICE_AUTH_TOKEN,
      queueName,
      role: "email-jobs",
      dlq: queueName === resources.emailDlq,
    };
  }
  if (queueName === resources.alertQueue || queueName === resources.alertDlq) {
    return {
      parse: parseOperationalAlert,
      namespace: environment.EMAIL_JOBS_CONTAINER,
      instanceName: resources.emailJobsInstance,
      path: "/jobs/email/alerts/process",
      authToken: environment.EMAIL_JOB_SERVICE_AUTH_TOKEN,
      queueName,
      role: "email-jobs",
      dlq: queueName === resources.alertDlq,
    };
  }
  return null;
};

const readJobDisposition = async (
  response: Response,
): Promise<{ terminal: boolean; reason: string }> => {
  if (!response.ok) {
    try {
      const value = (await response.clone().json()) as Record<string, unknown>;
      return {
        terminal: false,
        reason: sanitizeIdentifier(value.error, "job_response_error"),
      };
    } catch {
      return { terminal: false, reason: "job_response_error" };
    }
  }
  try {
    const value = (await response.clone().json()) as Record<string, unknown>;
    return {
      terminal: value.persisted === true && value.disposition === "terminal",
      reason: sanitizeIdentifier(value.reason, "unknown"),
    };
  } catch {
    return { terminal: false, reason: "invalid_job_response" };
  }
};

const payloadIdentifier = (payload: object): string => {
  const value = payload as Record<string, unknown>;
  return sanitizeIdentifier(value.job_id ?? value.reset_id ?? value.alert_id);
};

const retryDelaySeconds = async (response: Response): Promise<number | undefined> => {
  if (response.status !== 429 && response.status !== 503) {
    return undefined;
  }
  const headerDelay = parseRetryDelay(response.headers.get("retry-after"));
  if (headerDelay !== undefined) {
    return headerDelay;
  }
  try {
    const body = (await response.json()) as Record<string, unknown>;
    return parseRetryDelay(body.retry_after_seconds);
  } catch {
    return undefined;
  }
};

const parseRetryDelay = (value: unknown): number | undefined => {
  if (value === null || value === undefined || value === "") {
    return undefined;
  }
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) {
    return undefined;
  }
  const seconds = Math.floor(parsed);
  if (seconds < 1) {
    return undefined;
  }
  return Math.min(seconds, MAX_RETRY_DELAY_SECONDS);
};
