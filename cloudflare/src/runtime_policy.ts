export const turnstileEnabledForDeployment = (
  deploymentEnvironment: string,
): boolean => deploymentEnvironment !== "local";
