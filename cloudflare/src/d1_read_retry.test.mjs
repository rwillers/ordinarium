import assert from "node:assert/strict";
import test from "node:test";

import {
  isRetryableD1ReadError,
  retryD1Read,
} from "./d1_read_retry.ts";


test("D1 overload variants are recognized as retryable read errors", () => {
  assert.equal(
    isRetryableD1ReadError(
      new Error("D1_ERROR: D1 DB is overloaded. Requests queued for too long."),
    ),
    true,
  );
  assert.equal(
    isRetryableD1ReadError(
      new Error("D1_ERROR: D1 DB is overloaded. Too many requests queued."),
    ),
    true,
  );
});


test("D1 reads retry transient overloads with bounded jittered delays", async () => {
  let attempts = 0;
  const delays = [];
  const retryEvents = [];

  const result = await retryD1Read(
    async () => {
      attempts += 1;
      if (attempts < 3) {
        throw new Error(
          "D1_ERROR: D1 DB is overloaded. Requests queued for too long.",
        );
      }
      return "recovered";
    },
    {
      sleep: async (milliseconds) => delays.push(milliseconds),
      random: () => 0.5,
      onRetry: (event) => retryEvents.push(event),
    },
  );

  assert.equal(result, "recovered");
  assert.equal(attempts, 3);
  assert.deepEqual(delays, [250, 1_000]);
  assert.deepEqual(
    retryEvents.map(({ attempts: eventAttempts, retryDelayMs }) => ({
      attempts: eventAttempts,
      retryDelayMs,
    })),
    [
      { attempts: 1, retryDelayMs: 250 },
      { attempts: 2, retryDelayMs: 1_000 },
    ],
  );
});


test("D1 read retry propagates exhausted and non-transient failures", async () => {
  let overloadedAttempts = 0;
  await assert.rejects(
    retryD1Read(
      async () => {
        overloadedAttempts += 1;
        throw new Error(
          "D1_ERROR: D1 DB is overloaded. Too many requests queued.",
        );
      },
      { sleep: async () => {}, random: () => 0.5 },
    ),
    /Too many requests queued/,
  );
  assert.equal(overloadedAttempts, 4);

  let nonTransientAttempts = 0;
  await assert.rejects(
    retryD1Read(async () => {
      nonTransientAttempts += 1;
      throw new Error("D1_ERROR: no such table: missing");
    }),
    /no such table/,
  );
  assert.equal(nonTransientAttempts, 1);
});
