import assert from "node:assert/strict";
import test from "node:test";

import { redirectAliasToCanonicalOrigin } from "./canonical_origin.ts";


test("www requests redirect to the canonical origin", async () => {
  const response = redirectAliasToCanonicalOrigin(
    new Request("https://www.ordinarium.com/services?season=easter", {
      method: "POST",
    }),
    "https://ordinarium.com",
  );

  assert.equal(response.status, 308);
  assert.equal(
    response.headers.get("location"),
    "https://ordinarium.com/services?season=easter",
  );
});


test("canonical and unrelated hostnames are not redirected", () => {
  assert.equal(
    redirectAliasToCanonicalOrigin(
      new Request("https://ordinarium.com/login"),
      "https://ordinarium.com",
    ),
    null,
  );
  assert.equal(
    redirectAliasToCanonicalOrigin(
      new Request("https://other.example/login"),
      "https://ordinarium.com",
    ),
    null,
  );
});


test("path-like hostnames cannot escape the canonical origin", () => {
  const response = redirectAliasToCanonicalOrigin(
    new Request("https://www.ordinarium.com//other.example/path"),
    "https://ordinarium.com",
  );

  assert.equal(response.status, 308);
  assert.equal(
    response.headers.get("location"),
    "https://ordinarium.com//other.example/path",
  );
});


test("missing or invalid canonical origins do not redirect", () => {
  const request = new Request("https://www.ordinarium.com/login");

  assert.equal(redirectAliasToCanonicalOrigin(request), null);
  assert.equal(redirectAliasToCanonicalOrigin(request, "not-a-url"), null);
  assert.equal(
    redirectAliasToCanonicalOrigin(request, "https://ordinarium.com/path"),
    null,
  );
});
