import assert from "node:assert/strict";
import test from "node:test";

import { handleDocumentRequest } from "./document_orchestrator.ts";


class FakeDocumentNamespace {
  constructor(responseFactory = () => new Response("rendered")) {
    this.instanceNames = [];
    this.requests = [];
    this.responseFactory = responseFactory;
  }

  getByName(name) {
    this.instanceNames.push(name);
    return {
      fetch: async (request) => {
        this.requests.push(request);
        return this.responseFactory(request);
      },
    };
  }
}


const renderRequest = (options = {}) =>
  new Request("http://documents.internal/render", {
    method: "POST",
    body: JSON.stringify({ format: "pdf", html: "<p>ok</p>" }),
    headers: {
      authorization: "Bearer must-not-forward",
      cookie: "session=must-not-forward",
      "content-type": "application/json",
      "x-ordinarium-request-id": "request-123",
      ...options.headers,
    },
  });


test("orchestrator uses both document instances and injects only private headers", async () => {
  const namespace = new FakeDocumentNamespace();
  const environment = {
    DOCUMENT_CONTAINER: namespace,
    DOCUMENT_SERVICE_AUTH_TOKEN: "document-secret",
    DEPLOYMENT_ENV: "staging",
  };

  const first = await handleDocumentRequest(renderRequest(), environment);
  const second = await handleDocumentRequest(
    renderRequest({ headers: { "x-ordinarium-request-id": "request-456" } }),
    environment,
  );

  assert.equal(first.status, 200);
  assert.equal(second.status, 200);
  assert.equal(new Set(namespace.instanceNames).size, 2);
  assert.deepEqual(
    new Set(namespace.instanceNames),
    new Set(["staging-documents-0", "staging-documents-1"]),
  );
  for (const [index, request] of namespace.requests.entries()) {
    assert.equal(
      request.headers.get("x-ordinarium-document-auth"),
      "document-secret",
    );
    assert.equal(
      request.headers.get("x-ordinarium-request-id"),
      index === 0 ? "request-123" : "request-456",
    );
    assert.equal(request.headers.get("authorization"), null);
    assert.equal(request.headers.get("cookie"), null);
  }
});


test("orchestrator fails closed and permits only the bounded render contract", async () => {
  const namespace = new FakeDocumentNamespace();
  const missingSecret = await handleDocumentRequest(renderRequest(), {
    DOCUMENT_CONTAINER: namespace,
    DEPLOYMENT_ENV: "staging",
  });
  const wrongMethod = await handleDocumentRequest(
    new Request("http://documents.internal/render"),
    {
      DOCUMENT_CONTAINER: namespace,
      DOCUMENT_SERVICE_AUTH_TOKEN: "document-secret",
      DEPLOYMENT_ENV: "staging",
    },
  );
  const wrongPath = await handleDocumentRequest(
    new Request("http://documents.internal/health", { method: "POST" }),
    {
      DOCUMENT_CONTAINER: namespace,
      DOCUMENT_SERVICE_AUTH_TOKEN: "document-secret",
      DEPLOYMENT_ENV: "staging",
    },
  );
  const oversized = await handleDocumentRequest(
    renderRequest({ headers: { "content-length": String(5 * 1024 * 1024 + 1) } }),
    {
      DOCUMENT_CONTAINER: namespace,
      DOCUMENT_SERVICE_AUTH_TOKEN: "document-secret",
      DEPLOYMENT_ENV: "staging",
    },
  );

  assert.equal(missingSecret.status, 503);
  assert.equal(wrongMethod.status, 404);
  assert.equal(wrongPath.status, 404);
  assert.equal(oversized.status, 413);
  assert.equal(namespace.requests.length, 0);
});


test("orchestrator converts container and oversized-output failures to 503", async () => {
  const unavailableNamespace = {
    getByName() {
      return { fetch: async () => Promise.reject(new Error("capacity")) };
    },
  };
  const oversizedNamespace = new FakeDocumentNamespace(
    () =>
      new Response("oversized", {
        headers: { "content-length": String(25 * 1024 * 1024 + 1) },
      }),
  );

  const unavailable = await handleDocumentRequest(renderRequest(), {
    DOCUMENT_CONTAINER: unavailableNamespace,
    DOCUMENT_SERVICE_AUTH_TOKEN: "document-secret",
    DEPLOYMENT_ENV: "staging",
  });
  const oversized = await handleDocumentRequest(renderRequest(), {
    DOCUMENT_CONTAINER: oversizedNamespace,
    DOCUMENT_SERVICE_AUTH_TOKEN: "document-secret",
    DEPLOYMENT_ENV: "staging",
  });

  assert.equal(unavailable.status, 503);
  assert.equal(oversized.status, 503);
});
