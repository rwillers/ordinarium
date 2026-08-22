import type { D1ReadRetryOptions } from "./d1_read_retry.ts";
import {
  reconcilePasswordResetEmails,
  reconcilePcoRows,
  type EmailReconciliationEnvironment,
  type ReconciliationEnvironment,
} from "./queue_reconciliation.ts";

const RECONCILIATION_INTERVAL_MINUTES = 5;
const MILLISECONDS_PER_MINUTE = 60_000;

type ScheduledReconciliationEnvironment = ReconciliationEnvironment &
  EmailReconciliationEnvironment;

export const shouldRunScheduledReconciliation = (
  scheduledTime: number,
): boolean =>
  Number.isFinite(scheduledTime) &&
  Math.floor(scheduledTime / MILLISECONDS_PER_MINUTE) %
    RECONCILIATION_INTERVAL_MINUTES ===
    0;

export const reconcileScheduledQueues = async (
  environment: ScheduledReconciliationEnvironment,
  nowEpoch = Math.floor(Date.now() / 1_000),
  retryOptions: D1ReadRetryOptions = {},
): Promise<void> => {
  await reconcilePcoRows(environment, nowEpoch, retryOptions);
  await reconcilePasswordResetEmails(environment, nowEpoch, retryOptions);
};
