CREATE TABLE pco_connections (
  user_id INTEGER PRIMARY KEY,
  access_token TEXT NOT NULL,
  refresh_token TEXT,
  token_type TEXT,
  scope TEXT,
  expires_at TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE service_pco_links (
  id INTEGER PRIMARY KEY,
  service_id INTEGER NOT NULL,
  pco_service_type_id TEXT NOT NULL,
  pco_service_type_name TEXT,
  pco_plan_id TEXT NOT NULL,
  pco_plan_title TEXT,
  last_synced_at TEXT,
  last_sync_status TEXT,
  last_sync_error TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX idx_service_pco_links_service_id ON service_pco_links(service_id);
