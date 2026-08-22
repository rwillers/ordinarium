import assert from "node:assert/strict";
import test from "node:test";

import {
  reconcilePasswordResetEmails,
  reconcilePcoRows,
} from "./queue_reconciliation.ts";


class Statement {
  constructor(db, sql) {
    this.db = db;
    this.sql = sql;
    this.params = [];
  }

  bind(...params) {
    this.params = params;
    return this;
  }

  async all() {
    this.db.selects.push({ sql: this.sql, params: this.params });
    const rows = this.sql.includes("r.status='pending'")
      ? this.db.rows.filter((row) => row.status !== "retry")
      : this.db.rows;
    return { results: rows };
  }

  async run() {
    this.db.updates.push({ sql: this.sql, params: this.params });
    return { success: true };
  }
}


test("scheduled reconciliation republishes exact stale row messages", async () => {
  const db = {
    rows: [
      {
        job_id: "job-1",
        row_id: "row-1",
        user_id: 7,
        status: "pending",
        claim_expires_at: null,
      },
      {
        job_id: "job-1",
        row_id: "row-2",
        user_id: 7,
        status: "running",
        claim_expires_at: 900,
      },
      {
        job_id: "job-1",
        row_id: "row-retry",
        user_id: 7,
        status: "retry",
        claim_expires_at: null,
      },
    ],
    selects: [],
    updates: [],
    prepare(sql) {
      return new Statement(this, sql);
    },
  };
  const queue = {
    messages: [],
    async send(body) {
      this.messages.push(body);
    },
  };

  const count = await reconcilePcoRows(
    { APP_DB: db, PCO_JOBS_QUEUE: queue },
    1_000,
  );

  assert.equal(count, 2);
  assert.deepEqual(db.selects[0].params, [970, 1_000, 100]);
  assert.match(db.selects[0].sql, /r\.status='pending'/);
  assert.doesNotMatch(db.selects[0].sql, /pending','retry/);
  assert.deepEqual(queue.messages, [
    { job_id: "job-1", row_id: "row-1", user_id: 7 },
    { job_id: "job-1", row_id: "row-2", user_id: 7 },
  ]);
  assert.equal(db.updates.length, 2);
});


test("scheduled reconciliation leaves old retry rows to Queue backoff", async () => {
  const db = {
    rows: [
      {
        job_id: "job-1",
        row_id: "row-retry",
        user_id: 7,
        status: "retry",
        claim_expires_at: null,
      },
    ],
    selects: [],
    updates: [],
    prepare(sql) {
      return new Statement(this, sql);
    },
  };
  const messages = [];

  const count = await reconcilePcoRows(
    {
      APP_DB: db,
      PCO_JOBS_QUEUE: { send: async (body) => messages.push(body) },
    },
    10_000,
  );

  assert.equal(count, 0);
  assert.deepEqual(messages, []);
  assert.deepEqual(db.updates, []);
});


test("failed queue publication leaves row stale for the next cron", async () => {
  const db = {
    rows: [
      {
        job_id: "job-1",
        row_id: "row-1",
        user_id: 7,
        status: "pending",
        claim_expires_at: null,
      },
    ],
    updates: [],
    selects: [],
    prepare(sql) {
      return new Statement(this, sql);
    },
  };

  await assert.rejects(
    reconcilePcoRows(
      {
        APP_DB: db,
        PCO_JOBS_QUEUE: { send: async () => { throw new Error("queue down"); } },
      },
      1_000,
    ),
    /queue down/,
  );
  assert.deepEqual(db.updates, []);
});


class EmailStatement extends Statement {
  async all() {
    this.db.selects.push({ sql: this.sql, params: this.params });
    if (this.sql.includes("unixepoch(expires_at)<=?")) {
      return { results: this.db.expiredRows || [] };
    }
    return { results: this.db.recoverableRows || [] };
  }
}


const emailDb = ({ expiredRows = [], recoverableRows = [] } = {}) => ({
  expiredRows,
  recoverableRows,
  selects: [],
  updates: [],
  prepare(sql) {
    return new EmailStatement(this, sql);
  },
});


test("scheduled email recovery publishes only opaque stale reset IDs", async () => {
  const db = emailDb({
    recoverableRows: [
      {
        id: "reset-queued",
        delivery_status: "queued",
        delivery_claim_token: null,
        delivery_claim_expires_at: null,
      },
      {
        id: "reset-restart",
        delivery_status: "sending",
        delivery_claim_token: "dead-container",
        delivery_claim_expires_at: 900,
      },
    ],
  });
  const messages = [];

  const count = await reconcilePasswordResetEmails(
    {
      APP_DB: db,
      EMAIL_JOBS_QUEUE: { send: async (message) => messages.push(message) },
    },
    1_000,
  );

  assert.equal(count, 2);
  assert.deepEqual(messages, [
    { reset_id: "reset-queued" },
    { reset_id: "reset-restart" },
  ]);
  assert.deepEqual(db.selects[1].params, [1_000, 970, 1_000, 100]);
  assert.match(db.selects[1].sql, /delivery_status='queued'/);
  assert.match(db.selects[1].sql, /delivery_status='sending'/);
  assert.doesNotMatch(db.selects[1].sql, /delivery_status='retry'/);
  assert.equal(db.updates.length, 2);
});


test("scheduled email recovery terminalizes expired material with a capped scan", async () => {
  const db = emailDb({ expiredRows: [{ id: "reset-expired" }] });

  const count = await reconcilePasswordResetEmails(
    { APP_DB: db, EMAIL_JOBS_QUEUE: { send: async () => {} } },
    1_000,
  );

  assert.equal(count, 0);
  assert.deepEqual(db.selects[0].params, [1_000, 100]);
  assert.match(db.updates[0].sql, /delivery_token_envelope=null/);
  assert.deepEqual(db.updates[0].params, ["reset-expired", 1_000]);
});


test("failed email recovery publication leaves the row stale", async () => {
  const db = emailDb({
    recoverableRows: [
      {
        id: "reset-queued",
        delivery_status: "queued",
        delivery_claim_token: null,
        delivery_claim_expires_at: null,
      },
    ],
  });

  await assert.rejects(
    reconcilePasswordResetEmails(
      {
        APP_DB: db,
        EMAIL_JOBS_QUEUE: { send: async () => { throw new Error("queue down"); } },
      },
      1_000,
    ),
    /queue down/,
  );
  assert.deepEqual(db.updates, []);
});


test("scheduled reconciliation retries overloaded reads but not writes", async () => {
  let readAttempts = 0;
  let writeAttempts = 0;
  const delays = [];
  const db = {
    prepare(sql) {
      return {
        bind() {
          return this;
        },
        async all() {
          readAttempts += 1;
          if (readAttempts === 1) {
            throw new Error(
              "D1_ERROR: D1 DB is overloaded. Requests queued for too long.",
            );
          }
          return { results: [{ id: "reset-expired" }] };
        },
        async run() {
          writeAttempts += 1;
          throw new Error(
            "D1_ERROR: D1 DB is overloaded. Requests queued for too long.",
          );
        },
      };
    },
  };

  await assert.rejects(
    reconcilePasswordResetEmails(
      { APP_DB: db, EMAIL_JOBS_QUEUE: { send: async () => {} } },
      1_000,
      {
        sleep: async (milliseconds) => delays.push(milliseconds),
        random: () => 0.5,
      },
    ),
    /Requests queued for too long/,
  );

  assert.equal(readAttempts, 2);
  assert.equal(writeAttempts, 1);
  assert.deepEqual(delays, [250]);
});
