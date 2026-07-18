import assert from "node:assert/strict";
import test from "node:test";

import { handleEdgeRoute } from "./edge_routes.ts";


class FakeStatement {
  constructor(result) {
    this.result = result;
  }

  async first() {
    if (this.result instanceof Error) {
      throw this.result;
    }
    return this.result;
  }
}


class FakeDatabase {
  constructor(result = { ok: 1 }) {
    this.result = result;
    this.queries = [];
  }

  prepare(sql) {
    this.queries.push(sql);
    return new FakeStatement(this.result);
  }
}


const request = (path, options = {}) =>
  new Request(`https://ordinarium.example${path}`, options);


test("health is lightweight and does not query D1", async () => {
  const database = new FakeDatabase();
  const response = await handleEdgeRoute(request("/health"), {
    APP_DB: database,
    OPS_HEALTH_TOKEN: "ops-secret",
  });

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok" });
  assert.deepEqual(database.queries, []);
});


test("D1 operational health is protected", async () => {
  const database = new FakeDatabase();
  const missing = await handleEdgeRoute(request("/ops/d1-health"), {
    APP_DB: database,
    OPS_HEALTH_TOKEN: "ops-secret",
  });
  const authorized = await handleEdgeRoute(
    request("/ops/d1-health", {
      headers: { authorization: "Bearer ops-secret" },
    }),
    { APP_DB: database, OPS_HEALTH_TOKEN: "ops-secret" },
  );

  assert.equal(missing.status, 404);
  assert.equal(authorized.status, 200);
  assert.deepEqual(await authorized.json(), { status: "ok", database: "ok" });
  assert.deepEqual(database.queries, ["select 1 as ok"]);
});


test("D1 operational health reports an unavailable database", async () => {
  const response = await handleEdgeRoute(
    request("/ops/d1-health", {
      headers: { authorization: "Bearer ops-secret" },
    }),
    {
      APP_DB: new FakeDatabase(new Error("D1 unavailable")),
      OPS_HEALTH_TOKEN: "ops-secret",
    },
  );

  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), {
    status: "unavailable",
    database: "unavailable",
  });
});


test("non-edge routes fall through to the container", async () => {
  const response = await handleEdgeRoute(request("/services"), {
    APP_DB: new FakeDatabase(),
    OPS_HEALTH_TOKEN: "ops-secret",
  });

  assert.equal(response, null);
});
