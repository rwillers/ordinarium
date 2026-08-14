import assert from "node:assert/strict";
import test from "node:test";

import {
  handleObviousProbe,
  probeCategory,
} from "./edge_probe_filter.ts";


test("rejects foreign server-side application probes", () => {
  assert.equal(
    probeCategory("/assets/file-uploader/server/php/index.php"),
    "foreign_server_extension",
  );
  assert.equal(probeCategory("/XMLRPC.PHP"), "foreign_server_extension");
  assert.equal(probeCategory("/shell.phtml/execute"), "foreign_server_extension");
});


test("rejects sensitive dot paths and foreign platform probes", () => {
  assert.equal(probeCategory("/.env"), "sensitive_dot_path");
  assert.equal(probeCategory("/.git/config"), "sensitive_dot_path");
  assert.equal(probeCategory("/wp-admin/install"), "foreign_platform_path");
  assert.equal(probeCategory("/phpMyAdmin/"), "foreign_platform_path");
  assert.equal(
    probeCategory("/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php"),
    "foreign_server_extension",
  );
});


test("rejects encoded and malformed probe paths", () => {
  assert.equal(probeCategory("/%2eenv"), "sensitive_dot_path");
  assert.equal(probeCategory("/index%2ephp"), "foreign_server_extension");
  assert.equal(probeCategory("//wp-admin/install"), "foreign_platform_path");
  assert.equal(probeCategory("/%2Fphpmyadmin/"), "foreign_platform_path");
  assert.equal(probeCategory("/malformed%FFpath"), "malformed_path");
});


test("allows application and standards-based paths", () => {
  for (const path of [
    "/",
    "/services",
    "/service/123",
    "/page.php-safe",
    "/.well-known/security.txt",
    "/integrations/pco/callback",
  ]) {
    assert.equal(probeCategory(path), null, path);
  }
});


test("edge rejection is a quiet non-cacheable 404 with request correlation", () => {
  const response = handleObviousProbe(
    new Request("https://ordinarium.example/wp-login.php"),
    "request-id",
  );

  assert.equal(response.status, 404);
  assert.equal(response.headers.get("Cache-Control"), "private, no-store");
  assert.equal(response.headers.get("X-Ordinarium-Request-Id"), "request-id");
  assert.equal(response.body, null);
});


test("non-probe requests continue to normal edge routing", () => {
  const response = handleObviousProbe(
    new Request("https://ordinarium.example/services"),
    "request-id",
  );

  assert.equal(response, null);
});
