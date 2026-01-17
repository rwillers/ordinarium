CREATE TABLE service_custom_templates (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  text TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_service_custom_templates_user_id ON service_custom_templates(user_id);
CREATE INDEX idx_service_custom_templates_updated_at ON service_custom_templates(updated_at);
