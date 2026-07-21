import assert from "node:assert/strict";
import test from "node:test";

import {
  ALERT_DLQ_NAME,
  ALERT_QUEUE_NAME,
} from "./operational_alerts.ts";
import {
  EMAIL_DLQ_NAME,
  EMAIL_QUEUE_NAME,
  PCO_DLQ_NAME,
  PCO_QUEUE_NAME,
  handleQueueBatch,
} from "./queue_consumer.ts";
import { handleQueuePublishRequest } from "./queue_publisher.ts";


class FakeQueue {
  constructor(error = null) {
    this.error = error;
    this.messages = [];
  }

  async send(message) {
    if (this.error) {
      throw this.error;
    }
    this.messages.push(message);
  }
}


class FakeNamespace {
  constructor(responseFactory) {
    this.instanceNames = [];
    this.requests = [];
    this.responseFactory = responseFactory;
  }

  getByName(name) {
    this.instanceNames.push(name);
    return {
      fetch: async (request) => {
        this.requests.push(request);
        return this.responseFactory(request);
      },
    };
  }
}


const publisherEnvironment = (options = {}) => ({
  PCO_JOBS_QUEUE: options.pcoQueue || new FakeQueue(),
  EMAIL_JOBS_QUEUE: options.emailQueue || new FakeQueue(),
});


const publishRequest = (path, payload, options = {}) =>
  new Request(`http://queue.internal${path}`, {
    method: options.method || "POST",
    body: options.body || JSON.stringify(payload),
    headers: {
      "content-type": options.contentType || "application/json",
      authorization: "Bearer must-not-forward",
      cookie: "session=must-not-forward",
      ...options.headers,
    },
  });


const queueMessage = (body) => ({
  body,
  acknowledged: false,
  retryOptions: null,
  ack() {
    this.acknowledged = true;
  },
  retry(options) {
    this.retryOptions = options || {};
  },
});


const consumerEnvironment = (pcoResponse, emailResponse = pcoResponse) => ({
  PCO_JOBS_CONTAINER: new FakeNamespace(pcoResponse),
  EMAIL_JOBS_CONTAINER: new FakeNamespace(emailResponse),
  PCO_JOB_SERVICE_AUTH_TOKEN: "pco-job-secret",
  EMAIL_JOB_SERVICE_AUTH_TOKEN: "email-job-secret",
});


test("publisher queues only reconstructed row and reset contracts", async () => {
  const environment = publisherEnvironment();
  const pco = await handleQueuePublishRequest(
    publishRequest("/pco", { job_id: "job-1", row_id: "row-1", user_id: 7 }),
    environment,
  );
  const email = await handleQueuePublishRequest(
    publishRequest("/email", { reset_id: "reset-1" }),
    environment,
  );

  assert.equal(pco.status, 202);
  assert.equal(email.status, 202);
  assert.deepEqual(environment.PCO_JOBS_QUEUE.messages, [
    { job_id: "job-1", row_id: "row-1", user_id: 7 },
  ]);
  assert.deepEqual(environment.EMAIL_JOBS_QUEUE.messages, [
    { reset_id: "reset-1" },
  ]);
  assert.equal(JSON.stringify(environment).includes("must-not-forward"), false);
});


test("publisher rejects extra fields, wrong methods, media types, and large bodies", async () => {
  const environment = publisherEnvironment();
  const extra = await handleQueuePublishRequest(
    publishRequest("/pco", {
      job_id: "job-1",
      row_id: "row-1",
      user_id: 7,
      oauth_token: "secret",
    }),
    environment,
  );
  const wrongMethod = await handleQueuePublishRequest(
    new Request("http://queue.internal/pco"),
    environment,
  );
  const wrongType = await handleQueuePublishRequest(
    publishRequest("/email", { reset_id: "reset-1" }, { contentType: "text/plain" }),
    environment,
  );
  const oversized = await handleQueuePublishRequest(
    publishRequest("/email", { reset_id: "reset-1" }, {
      headers: { "content-length": "1025" },
    }),
    environment,
  );

  assert.equal(extra.status, 400);
  assert.equal(wrongMethod.status, 404);
  assert.equal(wrongType.status, 400);
  assert.equal(oversized.status, 413);
  assert.equal(environment.PCO_JOBS_QUEUE.messages.length, 0);
  assert.equal(environment.EMAIL_JOBS_QUEUE.messages.length, 0);
});


test("publisher reports queue send failures as unavailable", async () => {
  const response = await handleQueuePublishRequest(
    publishRequest("/email", { reset_id: "reset-1" }),
    publisherEnvironment({ emailQueue: new FakeQueue(new Error("capacity")) }),
  );

  assert.equal(response.status, 503);
});


test("consumer injects role auth and acks only persisted terminal responses", async () => {
  const environment = consumerEnvironment(
    () => Response.json({ disposition: "terminal", persisted: true }),
  );
  const message = queueMessage({ job_id: "job-1", row_id: "row-1", user_id: 7 });

  await handleQueueBatch({ queue: PCO_QUEUE_NAME, messages: [message] }, environment);

  assert.equal(message.acknowledged, true);
  assert.equal(message.retryOptions, null);
  assert.deepEqual(environment.PCO_JOBS_CONTAINER.instanceNames, ["staging-pco-jobs"]);
  const request = environment.PCO_JOBS_CONTAINER.requests[0];
  assert.equal(new URL(request.url).pathname, "/jobs/pco/rows/process");
  assert.equal(request.headers.get("x-ordinarium-job-auth"), "pco-job-secret");
  assert.equal(request.headers.get("authorization"), null);
  assert.equal(request.headers.get("cookie"), null);
  assert.deepEqual(await request.json(), {
    job_id: "job-1",
    row_id: "row-1",
    user_id: 7,
  });
});


test("consumer retries unavailable and incomplete success responses", async () => {
  const unavailable = consumerEnvironment(
    () => Response.json({ retry_after_seconds: 37 }, { status: 503 }),
  );
  const unavailableMessage = queueMessage({
    job_id: "job-1",
    row_id: "row-1",
    user_id: 7,
  });
  await handleQueueBatch(
    { queue: PCO_QUEUE_NAME, messages: [unavailableMessage] },
    unavailable,
  );

  const incomplete = consumerEnvironment(() => Response.json({ status: "ok" }));
  const incompleteMessage = queueMessage({
    job_id: "job-1",
    row_id: "row-1",
    user_id: 7,
  });
  await handleQueueBatch(
    { queue: PCO_QUEUE_NAME, messages: [incompleteMessage] },
    incomplete,
  );

  assert.deepEqual(unavailableMessage.retryOptions, { delaySeconds: 37 });
  assert.equal(unavailableMessage.acknowledged, false);
  assert.deepEqual(incompleteMessage.retryOptions, {});
  assert.equal(incompleteMessage.acknowledged, false);
});


test("consumer safely surfaces bounded retry reasons from job responses", async () => {
  const unavailable = consumerEnvironment(
    () =>
      Response.json(
        { error: "provider_configuration_missing", retry_after_seconds: 60 },
        { status: 503 },
      ),
  );
  const message = queueMessage({
    job_id: "job-1",
    row_id: "row-1",
    user_id: 7,
  });

  await handleQueueBatch(
    { queue: PCO_QUEUE_NAME, messages: [message] },
    unavailable,
  );

  assert.deepEqual(message.retryOptions, { delaySeconds: 60 });
  assert.equal(message.acknowledged, false);
});


test("consumer omits zero retry delay and clamps large delays to one day", async () => {
  const zeroDelay = consumerEnvironment(
    () => Response.json({ retry_after_seconds: 0 }, { status: 503 }),
  );
  const zeroMessage = queueMessage({
    job_id: "job-1",
    row_id: "row-1",
    user_id: 7,
  });
  await handleQueueBatch(
    { queue: PCO_QUEUE_NAME, messages: [zeroMessage] },
    zeroDelay,
  );

  const largeDelay = consumerEnvironment(
    () =>
      Response.json(
        { retry_after_seconds: 200_000 },
        { status: 429 },
      ),
  );
  const largeMessage = queueMessage({
    job_id: "job-1",
    row_id: "row-1",
    user_id: 7,
  });
  await handleQueueBatch(
    { queue: PCO_QUEUE_NAME, messages: [largeMessage] },
    largeDelay,
  );

  assert.deepEqual(zeroMessage.retryOptions, {});
  assert.deepEqual(largeMessage.retryOptions, { delaySeconds: 86_400 });
});


test("DLQ batches call role terminalization endpoints", async () => {
  const environment = consumerEnvironment(
    () => Response.json({ disposition: "terminal", persisted: true }),
  );
  const pcoMessage = queueMessage({
    job_id: "job-1",
    row_id: "row-1",
    user_id: 7,
  });
  const emailMessage = queueMessage({ reset_id: "reset-1" });

  await handleQueueBatch({ queue: PCO_DLQ_NAME, messages: [pcoMessage] }, environment);
  await handleQueueBatch({ queue: EMAIL_DLQ_NAME, messages: [emailMessage] }, environment);

  assert.equal(pcoMessage.acknowledged, true);
  assert.equal(emailMessage.acknowledged, true);
  assert.equal(
    new URL(environment.PCO_JOBS_CONTAINER.requests[0].url).pathname,
    "/jobs/pco/rows/dead-letter",
  );
  assert.equal(
    new URL(environment.EMAIL_JOBS_CONTAINER.requests[0].url).pathname,
    "/jobs/email/resets/dead-letter",
  );
  assert.equal(
    environment.EMAIL_JOBS_CONTAINER.requests[0].headers.get(
      "x-ordinarium-job-auth",
    ),
    "email-job-secret",
  );
});


test("alert queues deliver the bounded contract through the email role", async () => {
  const environment = consumerEnvironment(
    () => Response.json({ disposition: "terminal", persisted: true }),
  );
  const alert = {
    alert_id: "alert-1",
    kind: "d1_failure",
    severity: "critical",
    occurred_at: "2026-07-21T12:00:00.000Z",
    source: {
      script_name: "ordinarium-app-staging",
      container_role: "d1-bridge",
      queue: null,
      route: null,
      status: null,
      error_category: "internal",
      request_id: "request-1",
      job_id: null,
    },
  };
  const primary = queueMessage(alert);
  const deadLetter = queueMessage(alert);

  await handleQueueBatch({ queue: ALERT_QUEUE_NAME, messages: [primary] }, environment);
  await handleQueueBatch({ queue: ALERT_DLQ_NAME, messages: [deadLetter] }, environment);

  assert.equal(primary.acknowledged, true);
  assert.equal(deadLetter.acknowledged, true);
  assert.equal(environment.EMAIL_JOBS_CONTAINER.requests.length, 2);
  assert.equal(
    new URL(environment.EMAIL_JOBS_CONTAINER.requests[0].url).pathname,
    "/jobs/email/alerts/process",
  );
  assert.equal(
    environment.EMAIL_JOBS_CONTAINER.requests[0].headers.get(
      "x-ordinarium-job-auth",
    ),
    "email-job-secret",
  );
  assert.deepEqual(await environment.EMAIL_JOBS_CONTAINER.requests[0].json(), alert);
});


test("DLQ messages remain retryable during a terminalization outage", async () => {
  const environment = consumerEnvironment(
    () => Response.json({ retry_after_seconds: 60 }, { status: 503 }),
  );
  const message = queueMessage({
    job_id: "job-1",
    row_id: "row-1",
    user_id: 7,
  });

  await handleQueueBatch({ queue: PCO_DLQ_NAME, messages: [message] }, environment);

  assert.equal(message.acknowledged, false);
  assert.deepEqual(message.retryOptions, { delaySeconds: 60 });
});


test("consumer terminates malformed known messages but retries unknown queues", async () => {
  const environment = consumerEnvironment(
    () => Response.json({ disposition: "terminal", persisted: true }),
  );
  const malformed = queueMessage({ reset_id: "reset-1", token: "secret" });
  const unknown = queueMessage({ anything: true });

  await handleQueueBatch({ queue: EMAIL_QUEUE_NAME, messages: [malformed] }, environment);
  await handleQueueBatch({ queue: "unknown", messages: [unknown] }, environment);

  assert.equal(malformed.acknowledged, true);
  assert.equal(unknown.acknowledged, false);
  assert.deepEqual(unknown.retryOptions, {});
  assert.equal(environment.EMAIL_JOBS_CONTAINER.requests.length, 0);
  assert.equal(environment.PCO_JOBS_CONTAINER.requests.length, 0);
});
