import assert from "node:assert/strict";
import test from "node:test";

import { handleTurnstileRequest } from "./turnstile_gateway.ts";


test("Turnstile gateway forwards only the canonical Siteverify request", async () => {
  const forwarded = [];
  const request = new Request(
    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    {
      method: "POST",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        "x-container-only": "do-not-forward",
      },
      body: "secret=container-placeholder&response=token&remoteip=203.0.113.8&extra=drop-me",
    },
  );

  const response = await handleTurnstileRequest(
    request,
    { TURNSTILE_SECRET_KEY: "worker-secret" },
    async (forwardedRequest) => {
      forwarded.push(forwardedRequest);
      return Response.json({ success: true });
    },
  );

  assert.equal(response.status, 200);
  assert.equal(forwarded.length, 1);
  assert.equal(forwarded[0].url, request.url);
  assert.equal(forwarded[0].method, "POST");
  assert.equal(forwarded[0].headers.get("content-type"), "application/x-www-form-urlencoded");
  assert.equal(forwarded[0].headers.get("x-container-only"), null);
  assert.equal(
    await forwarded[0].text(),
    "secret=worker-secret&response=token&remoteip=203.0.113.8",
  );
});


test("Turnstile gateway rejects other methods, hosts, paths, and query strings", async () => {
  const requests = [
    new Request("https://challenges.cloudflare.com/turnstile/v0/siteverify"),
    new Request("https://example.com/turnstile/v0/siteverify", { method: "POST" }),
    new Request("https://challenges.cloudflare.com/other", { method: "POST" }),
    new Request(
      "https://challenges.cloudflare.com/turnstile/v0/siteverify?unexpected=true",
      { method: "POST" },
    ),
  ];

  for (const request of requests) {
    const response = await handleTurnstileRequest(
      request,
      { TURNSTILE_SECRET_KEY: "worker-secret" },
      async () => {
        throw new Error("request should not be forwarded");
      },
    );
    assert.equal(response.status, 404);
  }
});


test("Turnstile gateway converts transport failures into a safe response", async () => {
  const response = await handleTurnstileRequest(
    new Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: "response=token",
    }),
    { TURNSTILE_SECRET_KEY: "worker-secret" },
    async () => {
      throw new TypeError("secret-bearing network details");
    },
  );

  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), {
    success: false,
    "error-codes": ["internal-error"],
  });
});


test("Turnstile gateway preserves upstream failures", async () => {
  const response = await handleTurnstileRequest(
    new Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: "response=token",
    }),
    { TURNSTILE_SECRET_KEY: "worker-secret" },
    async () => Response.json(
      { success: false, "error-codes": ["invalid-input-secret"] },
      { status: 503 },
    ),
  );

  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), {
    success: false,
    "error-codes": ["invalid-input-secret"],
  });
});


test("Turnstile gateway bounds and validates the form body", async () => {
  const wrongContentType = await handleTurnstileRequest(
    new Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    }),
    { TURNSTILE_SECRET_KEY: "worker-secret" },
  );
  assert.equal(wrongContentType.status, 400);

  const oversized = await handleTurnstileRequest(
    new Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: "x".repeat(4097),
    }),
    { TURNSTILE_SECRET_KEY: "worker-secret" },
  );
  assert.equal(oversized.status, 413);
});


test("Turnstile gateway fails closed when the Worker secret is unavailable", async () => {
  const response = await handleTurnstileRequest(
    new Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: "response=token",
    }),
    {},
  );

  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), {
    success: false,
    "error-codes": ["internal-error"],
  });
});
