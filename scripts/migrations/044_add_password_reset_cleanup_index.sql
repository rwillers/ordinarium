CREATE INDEX idx_password_reset_expiry_cleanup
  ON password_reset_requests(delivery_status, expires_at, id)
  WHERE used_at IS NULL
    AND delivery_status IN ('queued','sending','retry');
