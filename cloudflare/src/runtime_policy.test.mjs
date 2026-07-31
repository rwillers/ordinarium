import assert from "node:assert/strict";
import test from "node:test";

import { turnstileEnabledForDeployment } from "./runtime_policy.ts";


test("Turnstile is enabled in deployed environments", () => {
  assert.equal(turnstileEnabledForDeployment("staging"), true);
  assert.equal(turnstileEnabledForDeployment("production"), true);
});


test("Turnstile is disabled only for local development", () => {
  assert.equal(turnstileEnabledForDeployment("local"), false);
});
