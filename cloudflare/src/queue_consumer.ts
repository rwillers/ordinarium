import { parseEmailMessage, parsePcoRowMessage } from "./queue_publisher.ts";

const JOB_AUTH_HEADER = "X-Ordinarium-Job-Auth";
const JOB_REQUEST_TIMEOUT_MS = 115_000;
const MAX_RETRY_DELAY_SECONDS = 86_400;

export const PCO_QUEUE_NAME = "ordinarium-app-staging-pco-jobs";
export const PCO_DLQ_NAME = `${PCO_QUEUE_NAME}-dlq`;
export const EMAIL_QUEUE_NAME = "ordinarium-app-staging-email-jobs";
export const EMAIL_DLQ_NAME = `${EMAIL_QUEUE_NAME}-dlq`;

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
}

interface QueueMessageLike {
  body: unknown;
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
  instanceName: () => string;
  path: string;
  authToken?: string;
}

let nextEmailInstance = 0;

export const handleQueueBatch = async (
  batch: QueueBatchLike,
  environment: QueueConsumerEnvironment,
): Promise<void> => {
  const route = routeForQueue(batch.queue, environment);
  if (!route) {
    console.error("Received a batch from an unknown queue", batch.queue);
    for (const message of batch.messages) {
      message.retry();
    }
    return;
  }

  for (const message of batch.messages) {
    const payload = route.parse(message.body);
    if (!payload) {
      console.error("Discarding malformed queue message", batch.queue);
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
  if (!route.authToken) {
    console.error("Job container authentication is not configured");
    message.retry();
    return;
  }

  const request = new Request(`http://jobs.internal${route.path}`, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "content-type": "application/json",
      [JOB_AUTH_HEADER]: route.authToken,
    },
    signal: AbortSignal.timeout(JOB_REQUEST_TIMEOUT_MS),
  });

  let response: Response;
  try {
    response = await route.namespace.getByName(route.instanceName()).fetch(request);
  } catch (error: unknown) {
    console.error("Job container request failed", error);
    message.retry();
    return;
  }

  if (await isPersistedTerminalResponse(response)) {
    message.ack();
    return;
  }
  const delaySeconds = await retryDelaySeconds(response);
  message.retry(delaySeconds === undefined ? undefined : { delaySeconds });
};

const routeForQueue = (
  queueName: string,
  environment: QueueConsumerEnvironment,
): ConsumerRoute | null => {
  if (queueName === PCO_QUEUE_NAME || queueName === PCO_DLQ_NAME) {
    // DLQ retries are finite even at the platform maximum. A later scheduled D1
    // reconciliation pass must terminalize stale records after a prolonged
    // container or D1 outage; queue delivery alone cannot guarantee that state.
    return {
      parse: parsePcoRowMessage,
      namespace: environment.PCO_JOBS_CONTAINER,
      instanceName: () => "staging-pco-jobs",
      path:
        queueName === PCO_QUEUE_NAME
          ? "/jobs/pco/rows/process"
          : "/jobs/pco/rows/dead-letter",
      authToken: environment.PCO_JOB_SERVICE_AUTH_TOKEN,
    };
  }
  if (queueName === EMAIL_QUEUE_NAME || queueName === EMAIL_DLQ_NAME) {
    return {
      parse: parseEmailMessage,
      namespace: environment.EMAIL_JOBS_CONTAINER,
      instanceName: selectEmailInstanceName,
      path:
        queueName === EMAIL_QUEUE_NAME
          ? "/jobs/email/resets/process"
          : "/jobs/email/resets/dead-letter",
      authToken: environment.EMAIL_JOB_SERVICE_AUTH_TOKEN,
    };
  }
  return null;
};

const selectEmailInstanceName = (): string => {
  const name = `staging-email-jobs-${nextEmailInstance}`;
  nextEmailInstance = (nextEmailInstance + 1) % 2;
  return name;
};

const isPersistedTerminalResponse = async (response: Response): Promise<boolean> => {
  if (!response.ok) {
    return false;
  }
  try {
    const value = (await response.clone().json()) as Record<string, unknown>;
    return value.persisted === true && value.disposition === "terminal";
  } catch {
    return false;
  }
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
