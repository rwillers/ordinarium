import assert from "node:assert/strict";
import test from "node:test";

import { emitQueueMetrics } from "./queue_observability.ts";


class FakeQueue {
  constructor(metrics) {
    this.value = metrics;
    this.calls = 0;
  }

  async metrics() {
    this.calls += 1;
    return this.value;
  }
}


test("scheduled queue observability reads primary and dead-letter backlogs", async () => {
  const metrics = {
    backlogCount: 0,
    backlogBytes: 0,
    oldestMessageTimestamp: undefined,
  };
  const environment = {
    PCO_JOBS_QUEUE: new FakeQueue(metrics),
    PCO_JOBS_DLQ: new FakeQueue(metrics),
    EMAIL_JOBS_QUEUE: new FakeQueue(metrics),
    EMAIL_JOBS_DLQ: new FakeQueue(metrics),
    DEPLOYMENT_ENV: "staging",
  };

  await emitQueueMetrics(environment, Date.parse("2026-07-18T12:00:00Z"));

  assert.deepEqual(
    Object.values(environment)
      .filter((value) => value instanceof FakeQueue)
      .map((queue) => queue.calls),
    [1, 1, 1, 1],
  );
});


test("queue observability labels production resources correctly", async () => {
  const metrics = {
    backlogCount: 0,
    backlogBytes: 0,
    oldestMessageTimestamp: undefined,
  };
  const environment = {
    PCO_JOBS_QUEUE: new FakeQueue(metrics),
    PCO_JOBS_DLQ: new FakeQueue(metrics),
    EMAIL_JOBS_QUEUE: new FakeQueue(metrics),
    EMAIL_JOBS_DLQ: new FakeQueue(metrics),
    DEPLOYMENT_ENV: "production",
  };
  const records = [];
  const originalInfo = console.info;
  console.info = (record) => records.push(record);
  try {
    await emitQueueMetrics(environment, Date.parse("2026-07-18T12:00:00Z"));
  } finally {
    console.info = originalInfo;
  }

  assert.deepEqual(
    records.map((record) => record.queue).sort(),
    [
      "ordinarium-app-production-email-jobs",
      "ordinarium-app-production-email-jobs-dlq",
      "ordinarium-app-production-pco-jobs",
      "ordinarium-app-production-pco-jobs-dlq",
    ],
  );
});
