CREATE TABLE service_pco_item_links (
  id INTEGER PRIMARY KEY,
  service_id INTEGER NOT NULL,
  ordinarium_token TEXT NOT NULL,
  pco_item_id TEXT NOT NULL,
  last_content_hash TEXT,
  last_position INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX idx_service_pco_item_links_service_token
  ON service_pco_item_links(service_id, ordinarium_token);

CREATE UNIQUE INDEX idx_service_pco_item_links_service_pco_item
  ON service_pco_item_links(service_id, pco_item_id);
