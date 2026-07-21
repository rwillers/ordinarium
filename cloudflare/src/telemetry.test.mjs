import assert from "node:assert/strict";
import test from "node:test";

import { errorCategory, sanitizeIdentifier, sanitizeRoute } from "./telemetry.ts";


test("telemetry route labels redact tokens and unstable identifiers", () => {
  assert.equal(
    sanitizeRoute("/reset-password/sensitive-reset-token"),
    "/reset-password/:token",
  );
  assert.equal(sanitizeRoute("/share/sensitive-share-token"), "/share/:token");
  assert.equal(sanitizeRoute("/service/123/view"), "/service/:id/view");
  assert.equal(
    sanitizeRoute("/service/550e8400-e29b-41d4-a716-446655440000/view"),
    "/service/:id/view",
  );
});


test("telemetry identifiers and errors collapse to bounded categories", () => {
  assert.equal(sanitizeIdentifier("job_123"), "job_123");
  assert.equal(sanitizeIdentifier("not allowed whitespace"), "unknown");
  assert.equal(errorCategory(new DOMException("timed out", "TimeoutError")), "timeout");
  assert.equal(errorCategory(new Error("secret-bearing details")), "internal");
});
