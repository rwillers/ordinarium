CREATE TABLE IF NOT EXISTS service_shares (
  id INTEGER PRIMARY KEY,
  service_id INTEGER NOT NULL,
  share_uuid TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_service_shares_service_id ON service_shares(service_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_service_shares_uuid ON service_shares(share_uuid);
