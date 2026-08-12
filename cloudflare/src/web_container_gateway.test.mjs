import assert from "node:assert/strict";
import test from "node:test";

import { fetchWebContainer } from "./web_container_gateway.ts";


class FakeContainer {
  constructor(responses) {
    this.responses = [...responses];
    this.requests = [];
  }

  async fetch(request) {
    this.requests.push(request);
    const response = this.responses.shift();
    if (response instanceof Error) {
      throw response;
    }
    return response;
  }
}


const transientResponse = (message = "Failed to start container: port timeout") =>
  new Response(message, {
    status: 500,
    headers: { "content-type": "text/plain;charset=UTF-8" },
  });


test("safe requests retry one recognized container startup failure", async () => {
  const container = new FakeContainer([
    transientResponse(),
    new Response("ready", { status: 200 }),
  ]);

  const result = await fetchWebContainer(
    container,
    new Request("https://ordinarium.com/login"),
  );

  assert.equal(result.response.status, 200);
  assert.equal(await result.response.text(), "ready");
  assert.equal(result.retryOutcome, "succeeded");
  assert.equal(container.requests.length, 2);
});


test("repeated transient startup failures become a controlled 503", async () => {
  const container = new FakeContainer([
    transientResponse(),
    transientResponse("Container suddenly disconnected, try again"),
  ]);

  const result = await fetchWebContainer(
    container,
    new Request("https://ordinarium.com/"),
  );

  assert.equal(result.response.status, 503);
  assert.equal(result.response.headers.get("retry-after"), "1");
  assert.deepEqual(await result.response.json(), {
    error: "web_container_unavailable",
  });
  assert.equal(result.retryOutcome, "exhausted");
  assert.equal(container.requests.length, 2);
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
  assert.equal(container.requests.length, 1);
});
