import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";


export const REQUIRED_QUEUE_NAMES = Object.freeze([
  "ordinarium-app-staging-pco-jobs",
  "ordinarium-app-staging-pco-jobs-dlq",
  "ordinarium-app-staging-email-jobs",
  "ordinarium-app-staging-email-jobs-dlq",
]);


export const ensureQueues = ({ run = runWrangler, log = console.log } = {}) => {
  for (const queueName of REQUIRED_QUEUE_NAMES) {
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

  for (const queueName of REQUIRED_QUEUE_NAMES) {
    const verification = run(["queues", "info", queueName]);
    if (!isVerifiedQueue(verification, queueName)) {
      throw new Error(`Remote queue verification incomplete: ${queueName}`);
    }
  }
  log(`Verified all ${REQUIRED_QUEUE_NAMES.length} required queues.`);
};


const runWrangler = (args) => {
  const scriptDirectory = fileURLToPath(new URL(".", import.meta.url));
  const wranglerPath = fileURLToPath(
    new URL("../node_modules/.bin/wrangler", import.meta.url),
  );
  const configPath = fileURLToPath(new URL("../wrangler.jsonc", import.meta.url));
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
    ensureQueues();
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  }
}
