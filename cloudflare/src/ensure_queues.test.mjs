import assert from "node:assert/strict";
import test from "node:test";

import {
  REQUIRED_QUEUE_NAMES,
  ensureQueues,
  queueNamesForEnvironment,
} from "../scripts/ensure-queues.mjs";


const result = (status, output) => ({ status, stdout: output, stderr: "" });


test("queue names are isolated by deployment environment", () => {
  assert.deepEqual(
    queueNamesForEnvironment("production"),
    REQUIRED_QUEUE_NAMES.map((name) => name.replace("-staging-", "-production-")),
  );
  assert.throws(() => queueNamesForEnvironment("preview"), /Unsupported queue environment/);
});


test("queue provisioning accepts existing queues and verifies all of them", () => {
  const calls = [];
  const run = (args) => {
    calls.push(args);
    return result(0, `Queue Name: ${args[2]}`);
  };

  ensureQueues({ run, log: () => {} });

  assert.equal(calls.length, REQUIRED_QUEUE_NAMES.length * 2);
  assert.equal(calls.some((args) => args[1] === "create"), false);
});


test("queue provisioning creates only confirmed missing queues", () => {
  const existing = new Set(REQUIRED_QUEUE_NAMES.slice(1));
  const calls = [];
  const run = (args) => {
    calls.push(args);
    const queueName = args[2];
    if (args[1] === "create") {
      existing.add(queueName);
      return result(0, `Created queue ${queueName}`);
    }
    if (existing.has(queueName)) {
      return result(0, `Queue Name: ${queueName}`);
    }
    return result(1, `Queue "${queueName}" does not exist`);
  };

  ensureQueues({ run, log: () => {} });

  assert.deepEqual(
    calls.filter((args) => args[1] === "create"),
    [["queues", "create", REQUIRED_QUEUE_NAMES[0]]],
  );
});


test("queue provisioning stops on an unverified inspection failure", () => {
  const calls = [];
  const run = (args) => {
    calls.push(args);
    return result(1, "Authentication failed");
  };

  assert.throws(
    () => ensureQueues({ run, log: () => {} }),
    /Unable to inspect required queue/,
  );
  assert.equal(calls.some((args) => args[1] === "create"), false);
});


test("queue provisioning fails when final remote verification is incomplete", () => {
  let inspectionCount = 0;
  const run = (args) => {
    if (args[1] !== "info") {
      throw new Error("unexpected create");
    }
    inspectionCount += 1;
    const queueName = args[2];
    if (inspectionCount > REQUIRED_QUEUE_NAMES.length && queueName === REQUIRED_QUEUE_NAMES[2]) {
      return result(0, "Queue Name: unexpected-queue");
    }
    return result(0, `Queue Name: ${queueName}`);
  };

  assert.throws(
    () => ensureQueues({ run, log: () => {} }),
    /Remote queue verification incomplete/,
  );
});


test("queue verification does not confuse a primary queue with its DLQ", () => {
  const primary = REQUIRED_QUEUE_NAMES[0];
  const run = (args) => {
    const queueName = args[2];
    if (queueName === primary) {
      return result(0, `Queue Name: ${primary}-dlq`);
    }
    return result(0, `Queue Name: ${queueName}`);
  };

  assert.throws(
    () => ensureQueues({ run, log: () => {} }),
    /Unable to inspect required queue/,
  );
});
