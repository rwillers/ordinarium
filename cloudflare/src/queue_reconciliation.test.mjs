import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

import {
  reconcilePasswordResetEmails,
  reconcilePcoRows,
  terminalizeExpiredPasswordResets,
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
    return { results: this.db.recoverableRows || [] };
  }
}


const emailDb = ({ recoverableRows = [] } = {}) => ({
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
  assert.deepEqual(db.selects[0].params, [1_000, 970, 1_000, 100]);
  assert.match(db.selects[0].sql, /delivery_status='queued'/);
  assert.match(db.selects[0].sql, /delivery_status='sending'/);
  assert.doesNotMatch(db.selects[0].sql, /delivery_status='retry'/);
  assert.equal(db.updates.length, 2);
});


test("expired reset cleanup is one bounded atomic update", async () => {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(`
    create table password_reset_requests (
      id text primary key,
      expires_at text not null,
      used_at text,
      delivery_status text not null,
      delivery_last_error text,
      delivery_failed_at text,
      delivery_token_envelope text,
      delivery_claim_token text,
      delivery_claim_expires_at integer,
      delivery_updated_at text
    );
    create index idx_password_reset_expiry_cleanup
      on password_reset_requests(delivery_status, expires_at, id)
      where used_at is null
        and delivery_status in ('queued','sending','retry');
  `);
  const insert = sqlite.prepare(`
    insert into password_reset_requests (
      id, expires_at, used_at, delivery_status, delivery_token_envelope,
      delivery_claim_token, delivery_claim_expires_at, delivery_updated_at
    ) values (?, datetime(?, 'unixepoch'), ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
  `);
  insert.run("expired", 900, null, "sending", "secret", "lease", 1_100);
  insert.run("terminal", 900, null, "sent", "terminal-secret", null, null);
  insert.run("used", 900, "1970-01-01 00:15:00", "queued", "used-secret", null, null);
  insert.run("future", 1_100, null, "queued", "future-secret", null, null);
  sqlite.exec("begin");
  for (let index = 0; index < 2_000; index += 1) {
    insert.run(
      `terminal-history-${String(index).padStart(4, "0")}`,
      100 + index % 500,
      null,
      "sent",
      "historical-secret",
      null,
      null,
    );
  }
  sqlite.exec("commit");

  const writes = [];
  let queryPlan = [];
  const database = {
    prepare(sql) {
      const state = { params: [] };
      return {
        bind(...params) {
          state.params = params;
          return this;
        },
        async run() {
          writes.push({ sql, params: state.params });
          queryPlan = sqlite.prepare(`explain query plan ${sql}`)
            .all(...state.params)
            .map((row) => ({ ...row }));
          const result = sqlite.prepare(sql).run(...state.params);
          return { success: true, meta: { changes: Number(result.changes) } };
        },
      };
    },
  };

  await terminalizeExpiredPasswordResets({ APP_DB: database }, 1_000);

  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0].params, [1_000, 100]);
  assert.match(writes[0].sql, /limit \?/);
  assert.match(writes[0].sql, /delivery_token_envelope=null/);
  assert.match(writes[0].sql, /expires_at<=datetime\(\?, 'unixepoch'\)/);
  assert.match(writes[0].sql, /delivery_status in \('queued','sending','retry'\)/);
  assert.ok(
    queryPlan.some((row) =>
      row.detail.includes("idx_password_reset_expiry_cleanup") &&
      row.detail.includes("delivery_status=? AND expires_at<?"),
    ),
    JSON.stringify(queryPlan),
  );
  assert.equal(
    queryPlan.some((row) => row.detail === "SCAN password_reset_requests"),
    false,
  );
  const row = (id) => ({
    ...sqlite.prepare(`
      select delivery_status, delivery_last_error, delivery_failed_at,
             delivery_token_envelope, delivery_claim_token,
             delivery_claim_expires_at
        from password_reset_requests where id=?
    `).get(id),
  });
  assert.deepEqual(row("expired"), {
    delivery_status: "failed",
    delivery_last_error: "reset_expired",
    delivery_failed_at: row("expired").delivery_failed_at,
    delivery_token_envelope: null,
    delivery_claim_token: null,
    delivery_claim_expires_at: null,
  });
  assert.ok(row("expired").delivery_failed_at);
  assert.equal(row("future").delivery_status, "queued");
  assert.equal(row("future").delivery_token_envelope, "future-secret");
  assert.equal(row("terminal").delivery_status, "sent");
  assert.equal(row("terminal").delivery_token_envelope, "terminal-secret");
  assert.equal(row("used").delivery_status, "queued");
  assert.equal(row("used").delivery_token_envelope, "used-secret");
  assert.equal(
    sqlite.prepare(`
      select count(*) as count from password_reset_requests
       where id like 'terminal-history-%'
         and delivery_status='sent'
         and delivery_token_envelope='historical-secret'
    `).get().count,
    2_000,
  );
  sqlite.close();
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
