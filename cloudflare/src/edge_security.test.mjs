import assert from "node:assert/strict";
import test from "node:test";

import { handleEdgeRateLimit, rateLimitedRoute } from "./edge_security.ts";


class FakeLimiterNamespace {
  constructor({ success = true, error = null, retryAfter = 60 } = {}) {
    this.success = success;
    this.error = error;
    this.retryAfter = retryAfter;
    this.names = [];
    this.paths = [];
  }

  getByName(name) {
    this.names.push(name);
    return {
      fetch: async (request) => {
        this.paths.push(new URL(request.url).pathname);
        if (this.error) {
          throw this.error;
        }
        return Response.json({
          success: this.success,
          retry_after_seconds: this.retryAfter,
        });
      },
    };
  }
}


const environment = (overrides = {}) => ({
  AUTH_RATE_LIMITER: new FakeLimiterNamespace(),
  ...overrides,
});


test("auth rate limits are applied only to state-changing auth routes", async () => {
  assert.equal(rateLimitedRoute("GET", "/login"), null);
  assert.equal(rateLimitedRoute("POST", "/services"), null);
  assert.deepEqual(rateLimitedRoute("POST", "/login"), {
    limiterPath: "/login",
  });
  assert.deepEqual(rateLimitedRoute("POST", "/reset-password/opaque-token"), {
    limiterPath: "/password-reset",
  });
});


test("auth limiter keys isolate route families and client addresses", async () => {
  const env = environment();
  const response = await handleEdgeRateLimit(
    new Request("https://ordinarium.example/signup", {
      method: "POST",
      headers: { "CF-Connecting-IP": "203.0.113.8" },
    }),
    env,
    "request-id",
  );

  assert.equal(response, null);
  assert.deepEqual(env.AUTH_RATE_LIMITER.names, ["203.0.113.8"]);
  assert.deepEqual(env.AUTH_RATE_LIMITER.paths, ["/signup"]);
});


test("auth limiter prefers a stable Access identity without logging it", async () => {
  const env = environment();
  await handleEdgeRateLimit(
    new Request("https://ordinarium.example/login", {
      method: "POST",
      headers: {
        "CF-Access-Authenticated-User-Email": "Person@Example.com",
        "CF-Connecting-IP": "203.0.113.8",
      },
    }),
    env,
    "request-id",
  );

  assert.deepEqual(env.AUTH_RATE_LIMITER.names, ["person@example.com"]);
  assert.deepEqual(env.AUTH_RATE_LIMITER.paths, ["/login"]);
});


test("auth rate limits fail closed without forwarding to the container", async () => {
  const limited = await handleEdgeRateLimit(
    new Request("https://ordinarium.example/login", { method: "POST" }),
    environment({
      AUTH_RATE_LIMITER: new FakeLimiterNamespace({
        success: false,
        retryAfter: 37,
      }),
    }),
    "limited-request",
  );
  const unavailable = await handleEdgeRateLimit(
    new Request("https://ordinarium.example/reset-password", { method: "POST" }),
    environment({
      AUTH_RATE_LIMITER: new FakeLimiterNamespace({
        error: new Error("unavailable"),
      }),
    }),
    "unavailable-request",
  );

  assert.equal(limited.status, 429);
  assert.equal(limited.headers.get("Retry-After"), "37");
  assert.equal(limited.headers.get("X-Ordinarium-Request-Id"), "limited-request");
  assert.equal(unavailable.status, 503);
});
