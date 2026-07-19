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
