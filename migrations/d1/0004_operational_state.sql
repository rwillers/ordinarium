-- Reviewed successors to the experimental staging resilience migrations.
ALTER TABLE service_custom_elements ADD COLUMN stable_token TEXT;
CREATE UNIQUE INDEX idx_service_custom_elements_stable_token
  ON service_custom_elements(stable_token)
  WHERE stable_token IS NOT NULL;

ALTER TABLE services ADD COLUMN creation_token TEXT;
CREATE UNIQUE INDEX idx_services_creation_token
  ON services(creation_token)
  WHERE creation_token IS NOT NULL;

ALTER TABLE pco_connections ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE pco_connections ADD COLUMN refresh_claim_token TEXT;
ALTER TABLE pco_connections ADD COLUMN refresh_claim_expires_at INTEGER;

ALTER TABLE pco_batch_sync_jobs ADD COLUMN claim_token TEXT;
ALTER TABLE pco_batch_sync_jobs ADD COLUMN claim_expires_at INTEGER;
ALTER TABLE pco_batch_sync_jobs ADD COLUMN delivery_attempts INTEGER NOT NULL DEFAULT 0;

CREATE TABLE pco_plan_operations (
  id TEXT PRIMARY KEY,
  operation_key TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL,
  service_id INTEGER NOT NULL,
  mode TEXT NOT NULL,
  pco_service_type_id TEXT NOT NULL,
  pco_service_type_name TEXT,
  pco_plan_id TEXT,
  pco_plan_title TEXT,
  baseline_plan_ids_json TEXT,
  plan_date TEXT,
  plan_time TEXT,
  timezone_offset INTEGER,
  template_id TEXT,
  series_title TEXT,
  step TEXT NOT NULL DEFAULT 'pending',
  status TEXT NOT NULL DEFAULT 'pending',
  error_category TEXT,
  claim_token TEXT,
  claim_expires_at INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
);
CREATE INDEX idx_pco_plan_operations_service
  ON pco_plan_operations(service_id, status);
CREATE INDEX idx_pco_plan_operations_claim
  ON pco_plan_operations(claim_expires_at);

CREATE TABLE pco_service_sync_leases (
  service_id INTEGER PRIMARY KEY,
  claim_token TEXT NOT NULL,
  claim_expires_at INTEGER NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
);
CREATE INDEX idx_pco_service_sync_leases_expiry
  ON pco_service_sync_leases(claim_expires_at);

CREATE TABLE pco_rate_limit_windows (
  user_id INTEGER PRIMARY KEY,
  window_started_at INTEGER NOT NULL,
  period_seconds INTEGER NOT NULL DEFAULT 20,
  request_limit INTEGER NOT NULL DEFAULT 100,
  request_count INTEGER NOT NULL DEFAULT 0,
  blocked_until INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE pco_batch_sync_rows (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  row_index INTEGER NOT NULL,
  service_id INTEGER,
  mode TEXT NOT NULL,
  request_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  effective_service_type_id TEXT,
  effective_plan_id TEXT,
  plan_operation_id TEXT,
  claim_token TEXT,
  claim_expires_at INTEGER,
  result_json TEXT,
  error_category TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  FOREIGN KEY(job_id) REFERENCES pco_batch_sync_jobs(id) ON DELETE CASCADE,
  FOREIGN KEY(plan_operation_id) REFERENCES pco_plan_operations(id) ON DELETE SET NULL,
  UNIQUE(job_id, row_index)
);
CREATE INDEX idx_pco_batch_rows_job_status
  ON pco_batch_sync_rows(job_id, status, row_index);
CREATE INDEX idx_pco_batch_rows_claim
  ON pco_batch_sync_rows(status, claim_expires_at);

CREATE TABLE password_reset_requests (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  token_hash TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  delivery_token_envelope TEXT,
  claim_token TEXT,
  delivery_status TEXT NOT NULL DEFAULT 'queued'
    CHECK (delivery_status IN ('queued','sending','retry','sent','accepted','suppressed','failed')),
  delivery_attempts INTEGER NOT NULL DEFAULT 0,
  delivery_claim_token TEXT,
  delivery_claim_expires_at INTEGER,
  delivery_last_error TEXT,
  delivery_provider_id TEXT,
  sent_at TEXT,
  delivery_failed_at TEXT,
  delivery_updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX idx_password_reset_requests_token_hash
  ON password_reset_requests(token_hash);
CREATE INDEX idx_password_reset_requests_user_id
  ON password_reset_requests(user_id);
CREATE INDEX idx_password_reset_requests_expires_at
  ON password_reset_requests(expires_at);
CREATE INDEX idx_password_reset_delivery_state
  ON password_reset_requests(
    delivery_status,
    delivery_claim_expires_at,
    delivery_updated_at
  );
