CREATE TABLE pco_batch_sync_jobs (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  status TEXT NOT NULL,
  request_payload TEXT NOT NULL,
  results_json TEXT,
  summary_json TEXT,
  error TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  started_at TEXT,
  completed_at TEXT,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_pco_batch_sync_jobs_user_id ON pco_batch_sync_jobs(user_id);
CREATE INDEX idx_pco_batch_sync_jobs_status ON pco_batch_sync_jobs(status);
