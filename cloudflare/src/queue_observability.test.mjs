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
  };

  await emitQueueMetrics(environment, Date.parse("2026-07-18T12:00:00Z"));

  assert.deepEqual(
    Object.values(environment).map((queue) => queue.calls),
    [1, 1, 1, 1],
  );
});
