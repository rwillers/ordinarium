import assert from "node:assert/strict";
import test from "node:test";

import { handleD1Request } from "./d1_bridge.ts";


class FakeStatement {
  constructor(database, sql) {
    this.database = database;
    this.sql = sql;
    this.params = [];
  }

  bind(...params) {
    this.params = params;
    return this;
  }

  async first() {
    this.database.recordAttempt(this.sql);
    this.database.failIfConfigured(this.sql);
    if (this.sql.startsWith("update id_sequences")) {
      const sequence = this.params[0];
      const nextValue = this.database.sequences.get(sequence);
      if (nextValue === undefined) {
        return null;
      }
      this.database.sequences.set(sequence, nextValue + 1);
      return { id: nextValue };
    }
    return this.database.firstRow;
  }

  async run() {
    this.database.recordAttempt(this.sql);
    this.database.failIfConfigured(this.sql);
    return {
      results: this.database.rows,
      meta: {
        changes: 2,
        last_row_id: 17,
        rows_read: 3,
        rows_written: 2,
        duration: 1.25,
      },
    };
  }
}


class FakeDatabase {
  constructor() {
    this.firstRow = { id: 7, title: "Proof" };
    this.rows = [{ id: 7 }, { id: 8 }];
    this.sequences = new Map([["services", 11]]);
    this.attempts = new Map();
    this.failures = new Map();
  }

  prepare(sql) {
    return new FakeStatement(this, sql);
  }

  async batch(statements) {
    return Promise.all(statements.map((statement) => statement.run()));
  }

  recordAttempt(sql) {
    this.attempts.set(sql, (this.attempts.get(sql) || 0) + 1);
  }

  failIfConfigured(sql) {
    const remaining = this.failures.get(sql) || 0;
    if (remaining > 0) {
      this.failures.set(sql, remaining - 1);
      throw new Error(
        "D1_ERROR: D1 DB storage operation exceeded timeout which caused object to be reset.",
      );
    }
  }
}


const request = (payload, method = "POST") =>
  new Request("http://d1.internal/query", {
    method,
    body: method === "POST" ? JSON.stringify(payload) : undefined,
    headers: method === "POST" ? { "content-type": "application/json" } : {},
  });


test("bridge permits POST only and rejects unknown operations", async () => {
  const database = new FakeDatabase();
  const getResponse = await handleD1Request(request({}, "GET"), database);
  const unknownResponse = await handleD1Request(
    request({ operation: "raw" }),
    database,
  );

  assert.equal(getResponse.status, 405);
  assert.deepEqual(await getResponse.json(), {
    ok: false,
    error: "method_not_allowed",
  });
  assert.equal(unknownResponse.status, 400);
});


test("bridge rejects unbounded or non-scalar statement input", async () => {
  const database = new FakeDatabase();
  const nestedParamResponse = await handleD1Request(
    request({ operation: "execute", sql: "select ?", params: [{ id: 1 }] }),
    database,
  );
  const oversizedParamsResponse = await handleD1Request(
    request({ operation: "execute", sql: "select 1", params: Array(501).fill(1) }),
    database,
  );
  const emptyBatchResponse = await handleD1Request(
    request({ operation: "batch", statements: [] }),
    database,
  );

  assert.equal(nestedParamResponse.status, 400);
  assert.equal(oversizedParamsResponse.status, 400);
  assert.equal(emptyBatchResponse.status, 400);
});


test("bridge normalizes reads, mutations, and batches", async () => {
  const database = new FakeDatabase();
  const oneResponse = await handleD1Request(
    request({ operation: "fetch_one", sql: "select ?", params: [7] }),
    database,
  );
  const allResponse = await handleD1Request(
    request({ operation: "fetch_all", sql: "select id from services" }),
    database,
  );
  const batchResponse = await handleD1Request(
    request({
      operation: "batch",
      statements: [
        { sql: "insert into services (id) values (?)", params: [7] },
        { sql: "select id from services", params: [] },
      ],
    }),
    database,
  );

  assert.deepEqual(await oneResponse.json(), {
    ok: true,
    row: { id: 7, title: "Proof" },
  });
  const all = await allResponse.json();
  assert.deepEqual(all.rows, [{ id: 7 }, { id: 8 }]);
  assert.deepEqual(all.metadata, {
    changes: 2,
    last_row_id: 17,
    rows_read: 3,
    rows_written: 2,
    duration_ms: 1.25,
  });
  const batch = await batchResponse.json();
  assert.equal(batch.ok, true);
  assert.equal(batch.results.length, 2);
});


test("bridge allocates numeric IDs without reuse", async () => {
  const database = new FakeDatabase();
  const firstResponse = await handleD1Request(
    request({ operation: "allocate_id", sequence: "services" }),
    database,
  );
  const secondResponse = await handleD1Request(
    request({ operation: "allocate_id", sequence: "services" }),
    database,
  );
  const missingResponse = await handleD1Request(
    request({ operation: "allocate_id", sequence: "missing" }),
    database,
  );

  assert.deepEqual(await firstResponse.json(), { ok: true, id: 11 });
  assert.deepEqual(await secondResponse.json(), { ok: true, id: 12 });
  assert.equal(missingResponse.status, 400);
});


test("bridge retries transient reads with bounded backoff but never retries mutations", async () => {
  const database = new FakeDatabase();
  database.failures.set("select one", 1);
  database.failures.set("select all", 4);
  database.failures.set("update services set title = 'Changed'", 1);
  const delays = [];
  const retryOptions = {
    sleep: async (milliseconds) => delays.push(milliseconds),
    random: () => 0.5,
  };

  const recovered = await handleD1Request(
    request({ operation: "fetch_one", sql: "select one" }),
    database,
    retryOptions,
  );
  const exhausted = await handleD1Request(
    request({ operation: "fetch_all", sql: "select all" }),
    database,
    retryOptions,
  );
  const mutation = await handleD1Request(
    request({
      operation: "execute",
      sql: "update services set title = 'Changed'",
    }),
    database,
  );

  assert.equal(recovered.status, 200);
  assert.equal(exhausted.status, 503);
  assert.equal(mutation.status, 503);
  assert.equal(database.attempts.get("select one"), 2);
  assert.equal(database.attempts.get("select all"), 4);
  assert.equal(database.attempts.get("update services set title = 'Changed'"), 1);
  assert.deepEqual(delays, [250, 250, 1000, 2500]);
});


test("bridge does not retry non-transient read failures", async () => {
  const database = new FakeDatabase();
  database.failIfConfigured = (sql) => {
    database.recordedFailure = sql;
    throw new Error("D1_ERROR: no such table: missing");
  };
  const delays = [];

  const response = await handleD1Request(
    request({ operation: "fetch_one", sql: "select from missing" }),
    database,
    {
      sleep: async (milliseconds) => delays.push(milliseconds),
      random: () => 0.5,
    },
  );

  assert.equal(response.status, 503);
  assert.equal(database.attempts.get("select from missing"), 1);
  assert.deepEqual(delays, []);
});
