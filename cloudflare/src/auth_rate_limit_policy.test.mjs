import assert from "node:assert/strict";
import test from "node:test";

import { consumeRateLimit } from "./auth_rate_limit_policy.ts";


test("auth counters reject exactly after the configured rolling window limit", () => {
  const startedAt = Date.parse("2026-07-18T12:00:00Z");
  let counter;
  for (let attempt = 1; attempt <= 10; attempt += 1) {
    const result = consumeRateLimit(counter, startedAt + attempt, 10);
    counter = result.counter;
    assert.equal(result.outcome.success, true);
  }

  const limited = consumeRateLimit(counter, startedAt + 10_000, 10);
  assert.deepEqual(limited.outcome, {
    success: false,
    retry_after_seconds: 51,
    remaining: 0,
  });
});


test("auth counters reset after the rolling window expires", () => {
  const stored = { count: 10, window_started_at: 1_000 };
  const result = consumeRateLimit(stored, 61_000, 10);

  assert.deepEqual(result, {
    counter: { count: 1, window_started_at: 61_000 },
    outcome: { success: true, retry_after_seconds: 0, remaining: 9 },
  });
});
