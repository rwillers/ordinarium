import assert from "node:assert/strict";
import test from "node:test";

import { deploymentResources } from "./deployment_resources.ts";


test("deployment resources isolate staging and production names", () => {
  const staging = deploymentResources("staging");
  const production = deploymentResources("production");

  assert.equal(staging.webInstance, "staging-web");
  assert.equal(production.webInstance, "production-web");
  assert.equal(production.pcoJobsInstance, "production-pco-jobs");
  assert.equal(production.pcoQueue, "ordinarium-app-production-pco-jobs");
  assert.equal(production.alertDlq, "ordinarium-app-production-alerts-dlq");
  assert.match(
    production.documentInstance("request-1"),
    /^production-documents-[01]$/,
  );
  assert.match(
    production.emailJobsInstance("job-1"),
    /^production-email-jobs-[01]$/,
  );
  assert.equal(
    production.emailJobsInstance("job-1"),
    production.emailJobsInstance("job-1"),
  );
});


test("deployment resources reject unsafe environment names", () => {
  assert.throws(
    () => deploymentResources("production/other"),
    /Invalid deployment environment/,
  );
});
