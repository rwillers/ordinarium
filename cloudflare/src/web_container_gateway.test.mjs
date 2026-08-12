import assert from "node:assert/strict";
import test from "node:test";

import { fetchWebContainer } from "./web_container_gateway.ts";


class FakeContainer {
  constructor(responses) {
    this.responses = [...responses];
    this.requests = [];
  }

  async fetchWithReadiness(request, forceReadinessCheck) {
    this.requests.push(request);
    this.forceReadinessChecks ||= [];
    this.forceReadinessChecks.push(forceReadinessCheck);
    const response = this.responses.shift();
    if (response instanceof Error) {
      throw response;
    }
    return response;
  }
}

const immediateRetries = {
  sleep: async () => undefined,
  random: () => 0.5,
};

const transientResponse = (message = "Failed to start container: port timeout") =>
  new Response(message, {
    status: 500,
    headers: { "content-type": "text/plain;charset=UTF-8" },
  });


test("safe requests retry recognized container startup failures", async () => {
  const container = new FakeContainer([
    transientResponse(),
    new Response("ready", { status: 200 }),
  ]);

  const result = await fetchWebContainer(
    container,
    new Request("https://ordinarium.com/login"),
    immediateRetries,
  );

  assert.equal(result.response.status, 200);
  assert.equal(await result.response.text(), "ready");
  assert.equal(result.retryOutcome, "succeeded");
  assert.equal(result.attempts, 2);
  assert.equal(container.requests.length, 2);
  assert.deepEqual(container.forceReadinessChecks, [false, true]);
});


test("repeated transient startup failures become a controlled 503", async () => {
  const container = new FakeContainer([
    transientResponse(),
    transientResponse("Container suddenly disconnected, try again"),
    new Response("There is no Container instance available at this time.", {
      status: 503,
    }),
  ]);

  const result = await fetchWebContainer(
    container,
    new Request("https://ordinarium.com/"),
    immediateRetries,
  );

  assert.equal(result.response.status, 503);
  assert.equal(result.response.headers.get("retry-after"), "1");
  assert.deepEqual(await result.response.json(), {
    error: "web_container_unavailable",
  });
  assert.equal(result.retryOutcome, "exhausted");
  assert.equal(result.attempts, 3);
  assert.equal(container.requests.length, 3);
  assert.deepEqual(container.forceReadinessChecks, [false, true, true]);
});


test("safe requests recover from a thrown container RPC failure", async () => {
  const container = new FakeContainer([
    new Error("internal container RPC error"),
    new Response("ready", { status: 200 }),
  ]);

  const result = await fetchWebContainer(
    container,
    new Request("https://ordinarium.com/"),
    immediateRetries,
  );

  assert.equal(result.response.status, 200);
  assert.equal(result.retryOutcome, "succeeded");
  assert.equal(result.attempts, 2);
  assert.deepEqual(container.forceReadinessChecks, [false, true]);
});


test("temporary platform HTTP statuses are retried", async () => {
  const container = new FakeContainer([
    new Response("rate limited", { status: 429 }),
    new Response("bad gateway", { status: 502 }),
    new Response("ready", { status: 200 }),
  ]);

  const result = await fetchWebContainer(
    container,
    new Request("https://ordinarium.com/"),
    immediateRetries,
  );

  assert.equal(result.response.status, 200);
  assert.equal(result.retryOutcome, "succeeded");
  assert.equal(result.attempts, 3);
  assert.deepEqual(container.forceReadinessChecks, [false, false, false]);
});


test("application 503 retries without forcing a redundant readiness probe", async () => {
  const container = new FakeContainer([
    Response.json({ error: "database_unavailable" }, { status: 503 }),
    new Response("ready", { status: 200 }),
  ]);

  const result = await fetchWebContainer(
    container,
    new Request("https://ordinarium.com/"),
    immediateRetries,
  );

  assert.equal(result.response.status, 200);
  assert.equal(result.retryOutcome, "succeeded");
  assert.deepEqual(container.forceReadinessChecks, [false, false]);
});


test("application 500 responses are not retried", async () => {
  const applicationFailure = new Response("<h1>Internal Server Error</h1>", {
    status: 500,
    headers: { "content-type": "text/html;charset=utf-8" },
  });
  const container = new FakeContainer([applicationFailure]);

  const result = await fetchWebContainer(
    container,
    new Request("https://ordinarium.com/service/1"),
  );

  assert.equal(result.response.status, 500);
  assert.equal(result.retryOutcome, "none");
  assert.equal(result.attempts, 1);
  assert.equal(container.requests.length, 1);
});


test("unrecognized text application failures are not retried", async () => {
  const applicationFailure = new Response("Application request failed", {
    status: 500,
    headers: { "content-type": "text/plain;charset=UTF-8" },
  });
  const container = new FakeContainer([applicationFailure]);

  const result = await fetchWebContainer(
    container,
    new Request("https://ordinarium.com/service/1"),
  );

  assert.equal(result.response.status, 500);
  assert.equal(result.retryOutcome, "none");
  assert.equal(result.attempts, 1);
  assert.equal(container.requests.length, 1);
});


test("oversized text failures return without waiting for clone cancellation", async () => {
  const body = "Failed to start container:" + "x".repeat(1024);
  const applicationFailure = new Response(body, {
    status: 500,
    headers: { "content-type": "text/plain;charset=UTF-8" },
  });
  const container = new FakeContainer([applicationFailure]);

  const result = await Promise.race([
    fetchWebContainer(
      container,
      new Request("https://ordinarium.com/service/1"),
    ),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error("fetchWebContainer timed out")), 250),
    ),
  ]);

  assert.equal(result.response.status, 500);
  assert.equal(await result.response.text(), body);
  assert.equal(result.retryOutcome, "none");
  assert.equal(result.attempts, 1);
  assert.equal(container.requests.length, 1);
});


test("unsafe requests are never retried", async () => {
  const container = new FakeContainer([transientResponse()]);

  const result = await fetchWebContainer(
    container,
    new Request("https://ordinarium.com/login", { method: "POST" }),
  );

  assert.equal(result.response.status, 500);
  assert.equal(result.retryOutcome, "none");
  assert.equal(result.attempts, 1);
  assert.equal(container.requests.length, 1);
  assert.deepEqual(container.forceReadinessChecks, [false]);
});


test("unsafe requests surface thrown failures without replaying", async () => {
  const error = new Error("container RPC unavailable");
  const container = new FakeContainer([error]);

  await assert.rejects(
    fetchWebContainer(
      container,
      new Request("https://ordinarium.com/login", { method: "POST" }),
      immediateRetries,
    ),
    error,
  );
  assert.equal(container.requests.length, 1);
});
