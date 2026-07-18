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
  }

  prepare(sql) {
    return new FakeStatement(this, sql);
  }

  async batch(statements) {
    return Promise.all(statements.map((statement) => statement.run()));
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
