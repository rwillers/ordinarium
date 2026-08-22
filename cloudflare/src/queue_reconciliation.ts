import {
  retryD1Read,
  type D1ReadRetryOptions,
} from "./d1_read_retry.ts";
import { emitTelemetry, errorCategory } from "./telemetry.ts";

const RECONCILIATION_LIMIT = 100;
const STALE_PENDING_SECONDS = 30;

interface RecoverablePcoRow {
  job_id: string;
  row_id: string;
  user_id: number;
  status: string;
  claim_expires_at: number | null;
}

export interface ReconciliationEnvironment {
  APP_DB: D1Database;
  PCO_JOBS_QUEUE: Queue;
}

interface RecoverablePasswordReset {
  id: string;
  delivery_status: string;
  delivery_claim_token: string | null;
  delivery_claim_expires_at: number | null;
}

export interface EmailReconciliationEnvironment {
  APP_DB: D1Database;
  EMAIL_JOBS_QUEUE: Queue;
}

export const reconcilePcoRows = async (
  environment: ReconciliationEnvironment,
  nowEpoch = Math.floor(Date.now() / 1000),
  retryOptions: D1ReadRetryOptions = {},
): Promise<number> => {
  const staleBefore = nowEpoch - STALE_PENDING_SECONDS;
  const result = await retryReconciliationRead(
    () => environment.APP_DB.prepare(
      `select r.id as row_id, r.job_id, j.user_id, r.status, r.claim_expires_at
       from pco_batch_sync_rows r
       join pco_batch_sync_jobs j on j.id=r.job_id
      where j.status != 'failed'
        and (
          (r.status='pending' and unixepoch(r.updated_at) <= ?)
          or (r.status='running' and coalesce(r.claim_expires_at, 0) <= ?)
        )
      order by r.updated_at, r.row_index, r.id
      limit ?`,
    )
      .bind(staleBefore, nowEpoch, RECONCILIATION_LIMIT)
      .all<RecoverablePcoRow>(),
    "pco_rows",
    retryOptions,
  );

  let published = 0;
  for (const row of result.results || []) {
    await environment.PCO_JOBS_QUEUE.send({
      job_id: row.job_id,
      row_id: row.row_id,
      user_id: Number(row.user_id),
    });
    await environment.APP_DB.prepare(
      `update pco_batch_sync_rows set updated_at=CURRENT_TIMESTAMP
        where id=? and job_id=? and status=?
          and coalesce(claim_expires_at, -1)=coalesce(?, -1)`,
    )
      .bind(
        row.row_id,
        row.job_id,
        row.status,
        row.claim_expires_at,
      )
      .run();
    published += 1;
  }
  return published;
};

export const reconcilePasswordResetEmails = async (
  environment: EmailReconciliationEnvironment,
  nowEpoch = Math.floor(Date.now() / 1000),
  retryOptions: D1ReadRetryOptions = {},
): Promise<number> => {
  const staleBefore = nowEpoch - STALE_PENDING_SECONDS;

  // Expired links must not retain decryptable delivery material indefinitely.
  const expired = await retryReconciliationRead(
    () => environment.APP_DB.prepare(
      `select id from password_reset_requests
      where used_at is null and unixepoch(expires_at)<=?
        and delivery_status not in ('sent','accepted','suppressed','failed')
      order by expires_at, id
      limit ?`,
    )
      .bind(nowEpoch, RECONCILIATION_LIMIT)
      .all<{ id: string }>(),
    "expired_password_resets",
    retryOptions,
  );
  for (const reset of expired.results || []) {
    await environment.APP_DB.prepare(
      `update password_reset_requests
          set delivery_status='failed', delivery_last_error='reset_expired',
              delivery_failed_at=CURRENT_TIMESTAMP,
              delivery_token_envelope=null, delivery_claim_token=null,
              delivery_claim_expires_at=null,
              delivery_updated_at=CURRENT_TIMESTAMP
        where id=? and used_at is null and unixepoch(expires_at)<=?
          and delivery_status not in ('sent','accepted','suppressed','failed')`,
    )
      .bind(reset.id, nowEpoch)
      .run();
  }

  const recoverable = await retryReconciliationRead(
    () => environment.APP_DB.prepare(
      `select id, delivery_status, delivery_claim_token,
            delivery_claim_expires_at
       from password_reset_requests
      where sent_at is null and used_at is null and unixepoch(expires_at)>?
        and (
          (delivery_status='queued' and unixepoch(delivery_updated_at)<=?)
          or (
            delivery_status='sending'
            and coalesce(delivery_claim_expires_at, 0)<=?
          )
        )
      order by delivery_updated_at, id
      limit ?`,
    )
      .bind(nowEpoch, staleBefore, nowEpoch, RECONCILIATION_LIMIT)
      .all<RecoverablePasswordReset>(),
    "recoverable_password_resets",
    retryOptions,
  );

  let published = 0;
  for (const reset of recoverable.results || []) {
    await environment.EMAIL_JOBS_QUEUE.send({ reset_id: reset.id });
    await environment.APP_DB.prepare(
      `update password_reset_requests
          set delivery_updated_at=CURRENT_TIMESTAMP
        where id=? and delivery_status=?
          and coalesce(delivery_claim_token, '')=coalesce(?, '')
          and coalesce(delivery_claim_expires_at, -1)=coalesce(?, -1)`,
    )
      .bind(
        reset.id,
        reset.delivery_status,
        reset.delivery_claim_token,
        reset.delivery_claim_expires_at,
      )
      .run();
    published += 1;
  }
  return published;
};

const retryReconciliationRead = <T>(
  operation: () => Promise<T>,
  task: string,
  options: D1ReadRetryOptions,
): Promise<T> =>
  retryD1Read(operation, {
    ...options,
    onRetry: ({ error, attempts, retryDelayMs }) => {
      emitTelemetry("warn", "d1_reconciliation_retry", {
        container_role: "d1-reconciliation",
        reconciliation_task: task,
        error_category: errorCategory(error),
        attempts,
        retry_delay_ms: retryDelayMs,
      });
    },
  });
