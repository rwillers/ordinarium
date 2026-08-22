import assert from "node:assert/strict";
import test from "node:test";

import {
  reconcileScheduledQueues,
  runScheduledReconciliation,
  scheduledReconciliationEnabled,
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


test("scheduled recovery supports an explicit environment circuit breaker", () => {
  assert.equal(scheduledReconciliationEnabled(undefined), true);
  assert.equal(scheduledReconciliationEnabled("true"), true);
  assert.equal(scheduledReconciliationEnabled("false"), false);
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

  assert.equal(selects.length, 2);
  assert.match(selects[0], /pco_batch_sync_rows/);
  assert.match(selects[1], /delivery_status='queued'/);
});


test("password reset recovery runs after PCO failure and the failure propagates", async () => {
  const attempts = [];
  const database = {
    prepare(sql) {
      return {
        bind() {
          return this;
        },
        async all() {
          if (sql.includes("pco_batch_sync_rows")) {
            attempts.push("pco");
            throw new Error("pco recovery failed");
          }
          attempts.push("email");
          return { results: [] };
        },
      };
    },
  };

  await assert.rejects(
    reconcileScheduledQueues(
      {
        APP_DB: database,
        PCO_JOBS_QUEUE: { send: async () => {} },
        EMAIL_JOBS_QUEUE: { send: async () => {} },
      },
      1_000,
    ),
    /pco recovery failed/,
  );

  assert.deepEqual(attempts, ["pco", "email"]);
});


test("production orchestration runs cleanup, PCO, and email sequentially", async () => {
  const attempts = [];
  const database = {
    prepare(sql) {
      return {
        bind() {
          return this;
        },
        async all() {
          attempts.push(sql.includes("pco_batch_sync_rows") ? "pco" : "email");
          return { results: [] };
        },
        async run() {
          attempts.push("cleanup");
          return { success: true };
        },
      };
    },
  };

  await runScheduledReconciliation(
    {
      APP_DB: database,
      PCO_JOBS_QUEUE: { send: async () => {} },
      EMAIL_JOBS_QUEUE: { send: async () => {} },
    },
    true,
    1_000,
  );

  assert.deepEqual(attempts, ["cleanup", "pco", "email"]);
});


test("production recovery continues after cleanup failure and rejects it", async () => {
  const attempts = [];
  const cleanupFailure = new Error("cleanup failed");
  const database = {
    prepare(sql) {
      return {
        bind() {
          return this;
        },
        async all() {
          attempts.push(sql.includes("pco_batch_sync_rows") ? "pco" : "email");
          return { results: [] };
        },
        async run() {
          attempts.push("cleanup");
          throw cleanupFailure;
        },
      };
    },
  };

  await assert.rejects(
    runScheduledReconciliation(
      {
        APP_DB: database,
        PCO_JOBS_QUEUE: { send: async () => {} },
        EMAIL_JOBS_QUEUE: { send: async () => {} },
      },
      true,
      1_000,
    ),
    (error) => error === cleanupFailure,
  );

  assert.deepEqual(attempts, ["cleanup", "pco", "email"]);
});


test("multiple failures propagate the raw D1 error after every task runs", async () => {
  const attempts = [];
  const d1Failure = new Error("D1_ERROR: D1 DB is overloaded.");
  const database = {
    prepare(sql) {
      return {
        bind() {
          return this;
        },
        async all() {
          if (sql.includes("pco_batch_sync_rows")) {
            attempts.push("pco");
            throw d1Failure;
          }
          attempts.push("email");
          throw new Error("email recovery failed");
        },
        async run() {
          attempts.push("cleanup");
          throw new Error("cleanup failed");
        },
      };
    },
  };

  await assert.rejects(
    runScheduledReconciliation(
      {
        APP_DB: database,
        PCO_JOBS_QUEUE: { send: async () => {} },
        EMAIL_JOBS_QUEUE: { send: async () => {} },
      },
      true,
      1_000,
    ),
    (error) => error === d1Failure,
  );

  assert.deepEqual(attempts, ["cleanup", "pco", "email"]);
});


test("disabled recovery still runs only expired reset cleanup", async () => {
  const statements = [];
  const database = {
    prepare(sql) {
      const statement = { sql, params: [] };
      statements.push(statement);
      return {
        bind(...params) {
          statement.params = params;
          return this;
        },
        async all() {
          throw new Error("recovery read must remain disabled");
        },
        async run() {
          return { success: true };
        },
      };
    },
  };

  await runScheduledReconciliation(
    {
      APP_DB: database,
      PCO_JOBS_QUEUE: {
        send: async () => { throw new Error("PCO publication disabled"); },
      },
      EMAIL_JOBS_QUEUE: {
        send: async () => { throw new Error("email publication disabled"); },
      },
    },
    false,
    1_000,
  );

  assert.equal(statements.length, 1);
  assert.match(statements[0].sql, /update password_reset_requests/);
  assert.match(statements[0].sql, /delivery_token_envelope=null/);
  assert.deepEqual(statements[0].params, [1_000, 100]);
});


test("disabled recovery propagates cleanup write failures without retrying", async () => {
  let writes = 0;
  const failure = new Error("cleanup write failed");
  const database = {
    prepare() {
      return {
        bind() {
          return this;
        },
        async run() {
          writes += 1;
          throw failure;
        },
      };
    },
  };

  await assert.rejects(
    runScheduledReconciliation(
      {
        APP_DB: database,
        PCO_JOBS_QUEUE: { send: async () => {} },
        EMAIL_JOBS_QUEUE: { send: async () => {} },
      },
      false,
      1_000,
    ),
    (error) => error === failure,
  );
  assert.equal(writes, 1);
});
