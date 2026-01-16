CREATE TABLE service_custom_elements (
  id INTEGER PRIMARY KEY,
  service_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  text TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_service_custom_elements_service_id ON service_custom_elements(service_id);
CREATE INDEX idx_service_custom_elements_user_id ON service_custom_elements(user_id);
