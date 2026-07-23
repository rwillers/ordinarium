import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";


export const queueNamesForEnvironment = (environment) => {
  if (!["staging", "production"].includes(environment)) {
    throw new Error(`Unsupported queue environment: ${environment}`);
  }
  const prefix = `ordinarium-app-${environment}`;
  return Object.freeze([
    `${prefix}-pco-jobs`,
    `${prefix}-pco-jobs-dlq`,
    `${prefix}-email-jobs`,
    `${prefix}-email-jobs-dlq`,
    `${prefix}-alerts`,
    `${prefix}-alerts-dlq`,
  ]);
};


export const REQUIRED_QUEUE_NAMES = queueNamesForEnvironment("staging");


export const ensureQueues = ({
  run = runWrangler,
  log = console.log,
  queueNames = REQUIRED_QUEUE_NAMES,
} = {}) => {
  for (const queueName of queueNames) {
    const inspection = run(["queues", "info", queueName]);
    if (isVerifiedQueue(inspection, queueName)) {
      log(`Verified existing queue: ${queueName}`);
      continue;
    }
    if (!queueDoesNotExist(inspection, queueName)) {
      throw new Error(`Unable to inspect required queue: ${queueName}`);
    }

    const creation = run(["queues", "create", queueName]);
    if (creation.status !== 0 && !queueAlreadyExists(creation, queueName)) {
      throw new Error(`Unable to create required queue: ${queueName}`);
    }
    log(`Ensured queue: ${queueName}`);
  }

  for (const queueName of queueNames) {
    const verification = run(["queues", "info", queueName]);
    if (!isVerifiedQueue(verification, queueName)) {
      throw new Error(`Remote queue verification incomplete: ${queueName}`);
    }
  }
  log(`Verified all ${queueNames.length} required queues.`);
};


const runWrangler = (args) => {
  const scriptDirectory = fileURLToPath(new URL(".", import.meta.url));
  const wranglerPath = fileURLToPath(
    new URL("../node_modules/.bin/wrangler", import.meta.url),
  );
  const configuredPath = process.env.ORDINARIUM_WRANGLER_CONFIG;
  const configPath = configuredPath
    ? resolve(process.cwd(), configuredPath)
    : fileURLToPath(new URL("../wrangler.jsonc", import.meta.url));
  const result = spawnSync(wranglerPath, [...args, "--config", configPath], {
    cwd: scriptDirectory,
    encoding: "utf8",
    env: process.env,
    maxBuffer: 1024 * 1024,
  });
  if (result.error) {
    throw result.error;
  }
  return {
    status: result.status,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
  };
};


const isVerifiedQueue = (result, queueName) =>
  result.status === 0 &&
  output(result)
    .split(/\r?\n/)
    .some((line) => line.trim() === `Queue Name: ${queueName}`);

const queueDoesNotExist = (result, queueName) =>
  result.status !== 0 &&
  output(result).includes(`Queue "${queueName}" does not exist`);

const queueAlreadyExists = (result, queueName) => {
  const message = output(result).toLowerCase();
  return message.includes(queueName.toLowerCase()) && message.includes("already exists");
};

const output = (result) => `${result.stdout}\n${result.stderr}`;


const isDirectInvocation =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isDirectInvocation) {
  try {
    const environment = process.env.ORDINARIUM_DEPLOYMENT_ENV || "staging";
    ensureQueues({ queueNames: queueNamesForEnvironment(environment) });
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  }
}
