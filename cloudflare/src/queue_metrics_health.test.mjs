import assert from "node:assert/strict";
import test from "node:test";
import { observeQueueMetrics, parseQueueMetricsObservation } from "./queue_metrics_health.ts";

const failed = (observed_at) => ({ healthy: false, observed_at });
const healthy = (observed_at) => ({ healthy: true, observed_at });

test("metrics visibility pages only after three readings spanning two minutes", () => {
  let result = observeQueueMetrics(undefined, failed(0));
  assert.equal(result.sustained, false);
  result = observeQueueMetrics(JSON.parse(JSON.stringify(result.state)), failed(60_000));
  assert.equal(result.sustained, false);
  result = observeQueueMetrics(result.state, failed(120_000));
  assert.equal(result.sustained, true);
  assert.equal(result.state.failures, 3);
});

test("duplicate and rapid failures cannot manufacture a sustained outage", () => {
  let result = observeQueueMetrics(undefined, failed(0));
  result = observeQueueMetrics(result.state, failed(0));
  assert.equal(result.state.failures, 1);
  result = observeQueueMetrics(result.state, failed(1));
  result = observeQueueMetrics(result.state, failed(2));
  assert.equal(result.sustained, false);
});

test("recovery resets the streak and rejects a late pre-recovery failure", () => {
  let result = observeQueueMetrics(undefined, failed(0));
  result = observeQueueMetrics(result.state, failed(60_000));
  result = observeQueueMetrics(result.state, healthy(120_000));
  assert.equal(result.state.failures, 0);
  result = observeQueueMetrics(result.state, failed(90_000));
  assert.equal(result.state.failures, 0);
  result = observeQueueMetrics(result.state, failed(180_000));
  assert.equal(result.sustained, false);
  assert.equal(result.state.first_failure_at, 180_000);
});

test("separated outages do not accumulate and duplicate sustained readings can retry paging", () => {
  let result = observeQueueMetrics(undefined, failed(0));
  result = observeQueueMetrics(result.state, failed(60_000));
  result = observeQueueMetrics(result.state, failed(300_000));
  assert.equal(result.state.failures, 1);
  result = observeQueueMetrics(result.state, failed(360_000));
  result = observeQueueMetrics(result.state, failed(420_000));
  assert.equal(result.sustained, true);
  assert.equal(observeQueueMetrics(result.state, failed(420_000)).sustained, true);
  assert.equal(observeQueueMetrics(result.state, healthy(360_000)).sustained, false);
});

test("metrics observations reject malformed or additional fields", () => {
  assert.deepEqual(parseQueueMetricsObservation(failed(0)), failed(0));
  for (const value of [null, {}, [], { healthy: 1, observed_at: 0 },
    failed(-1), failed(Infinity), failed(NaN), { ...failed(0), token: "secret" }]) {
    assert.equal(parseQueueMetricsObservation(value), null);
  }
});
