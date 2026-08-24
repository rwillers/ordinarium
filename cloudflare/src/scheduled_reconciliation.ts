import type { D1ReadRetryOptions } from "./d1_read_retry.ts";
import {
  reconcilePasswordResetEmails,
  reconcilePcoRows,
  terminalizeExpiredPasswordResets,
  type EmailReconciliationEnvironment,
  type PasswordResetCleanupEnvironment,
  type ReconciliationEnvironment,
} from "./queue_reconciliation.ts";

const RECONCILIATION_INTERVAL_MINUTES = 5;
const MILLISECONDS_PER_MINUTE = 60_000;

type ScheduledReconciliationEnvironment = ReconciliationEnvironment &
  EmailReconciliationEnvironment &
  PasswordResetCleanupEnvironment;

type ScheduledTask = () => Promise<unknown>;

export const shouldRunScheduledReconciliation = (
  scheduledTime: number,
): boolean =>
  Number.isFinite(scheduledTime) &&
  Math.floor(scheduledTime / MILLISECONDS_PER_MINUTE) %
    RECONCILIATION_INTERVAL_MINUTES ===
    0;

export const scheduledReconciliationEnabled = (
  configuredValue: string | undefined,
): boolean => configuredValue !== "false";

export const reconcileScheduledQueues = async (
  environment: ScheduledReconciliationEnvironment,
  nowEpoch = Math.floor(Date.now() / 1_000),
  retryOptions: D1ReadRetryOptions = {},
): Promise<void> => {
  await runSequentially(recoveryTasks(environment, nowEpoch, retryOptions));
};

export const runScheduledReconciliation = async (
  environment: ScheduledReconciliationEnvironment,
  reconciliationEnabled: boolean,
  nowEpoch = Math.floor(Date.now() / 1_000),
  retryOptions: D1ReadRetryOptions = {},
): Promise<void> => {
  if (!reconciliationEnabled) {
    return;
  }
  const tasks: ScheduledTask[] = [
    () => terminalizeExpiredPasswordResets(environment, nowEpoch),
    ...recoveryTasks(environment, nowEpoch, retryOptions),
  ];
  await runSequentially(tasks);
};

const recoveryTasks = (
  environment: ScheduledReconciliationEnvironment,
  nowEpoch: number,
  retryOptions: D1ReadRetryOptions,
): ScheduledTask[] => [
  () => reconcilePcoRows(environment, nowEpoch, retryOptions),
  () => reconcilePasswordResetEmails(environment, nowEpoch, retryOptions),
];

const runSequentially = async (tasks: ScheduledTask[]): Promise<void> => {
  const errors: unknown[] = [];
  for (const task of tasks) {
    try {
      await task();
    } catch (error: unknown) {
      errors.push(error);
    }
  }
  if (errors.length > 0) {
    throw errors.find(isD1Error) ?? errors[0];
  }
};

const isD1Error = (error: unknown): boolean => {
  const message = error instanceof Error ? error.message : String(error);
  return message.startsWith("D1_ERROR:");
};
