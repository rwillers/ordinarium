const DEPLOYMENT_NAME_PATTERN = /^[a-z][a-z0-9-]{0,31}$/;

export type DeploymentResources = {
  webInstance: string;
  documentInstance: (value: string) => string;
  pcoJobsInstance: string;
  emailJobsInstance: (value: string) => string;
  pcoQueue: string;
  pcoDlq: string;
  emailQueue: string;
  emailDlq: string;
  alertQueue: string;
  alertDlq: string;
};

export const deploymentResources = (
  deploymentEnvironment: string,
): DeploymentResources => {
  if (!DEPLOYMENT_NAME_PATTERN.test(deploymentEnvironment)) {
    throw new Error("Invalid deployment environment.");
  }

  const queuePrefix = `ordinarium-app-${deploymentEnvironment}`;
  return {
    webInstance: `${deploymentEnvironment}-web`,
    documentInstance: (value) =>
      `${deploymentEnvironment}-documents-${stableShard(value, 2)}`,
    pcoJobsInstance: `${deploymentEnvironment}-pco-jobs`,
    emailJobsInstance: (value) =>
      `${deploymentEnvironment}-email-jobs-${stableShard(value, 2)}`,
    pcoQueue: `${queuePrefix}-pco-jobs`,
    pcoDlq: `${queuePrefix}-pco-jobs-dlq`,
    emailQueue: `${queuePrefix}-email-jobs`,
    emailDlq: `${queuePrefix}-email-jobs-dlq`,
    alertQueue: `${queuePrefix}-alerts`,
    alertDlq: `${queuePrefix}-alerts-dlq`,
  };
};

const stableShard = (value: string, shardCount: number): number => {
  let hash = 2_166_136_261;
  for (const character of value) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16_777_619);
  }
  return (hash >>> 0) % shardCount;
};
