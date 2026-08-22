import assert from "node:assert/strict";
import test from "node:test";

import {
  reconcileScheduledQueues,
  shouldRunScheduledReconciliation,
} from "./scheduled_reconciliation.ts";


test("scheduled recovery runs once every five cron minutes", () => {
  assert.equal(
    shouldRunScheduledReconciliation(Date.parse("2026-08-22T12:35:08Z")),
    true,
  );
  assert.equal(
    shouldRunScheduledReconciliation(Date.parse("2026-08-22T12:36:08Z")),
    false,
  );
  assert.equal(
    shouldRunScheduledReconciliation(Date.parse("2026-08-22T12:40:59Z")),
    true,
  );
});


test("scheduled recovery serializes PCO and password reset reads", async () => {
  const selects = [];
  const database = {
    prepare(sql) {
      return {
        bind() {
          return this;
        },
        async all() {
          selects.push(sql);
          return { results: [] };
        },
      };
    },
  };

  await reconcileScheduledQueues(
    {
      APP_DB: database,
      PCO_JOBS_QUEUE: { send: async () => {} },
      EMAIL_JOBS_QUEUE: { send: async () => {} },
    },
    1_000,
  );

  assert.equal(selects.length, 3);
  assert.match(selects[0], /pco_batch_sync_rows/);
  assert.match(selects[1], /unixepoch\(expires_at\)<=\?/);
  assert.match(selects[2], /delivery_status='queued'/);
});
