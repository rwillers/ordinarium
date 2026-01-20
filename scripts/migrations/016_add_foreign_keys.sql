PRAGMA foreign_keys = OFF;
BEGIN;

DELETE FROM service_shares
WHERE service_id NOT IN (SELECT id FROM services);

DELETE FROM service_custom_elements
WHERE service_id NOT IN (SELECT id FROM services);

DELETE FROM service_custom_elements
WHERE user_id NOT IN (SELECT id FROM users);

DELETE FROM service_custom_templates
WHERE user_id NOT IN (SELECT id FROM users);

CREATE TABLE service_shares_new (
  id INTEGER PRIMARY KEY,
  service_id INTEGER NOT NULL,
  share_uuid TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
);

INSERT INTO service_shares_new (id, service_id, share_uuid, created_at)
SELECT id, service_id, share_uuid, created_at
FROM service_shares;

DROP TABLE service_shares;
ALTER TABLE service_shares_new RENAME TO service_shares;

CREATE INDEX idx_service_shares_service_id ON service_shares(service_id);
CREATE UNIQUE INDEX idx_service_shares_uuid ON service_shares(share_uuid);

CREATE TABLE service_custom_elements_new (
  id INTEGER PRIMARY KEY,
  service_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  text TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

INSERT INTO service_custom_elements_new (id, service_id, user_id, title, text, created_at)
SELECT id, service_id, user_id, title, text, created_at
FROM service_custom_elements;

DROP TABLE service_custom_elements;
ALTER TABLE service_custom_elements_new RENAME TO service_custom_elements;

CREATE INDEX idx_service_custom_elements_service_id ON service_custom_elements(service_id);
CREATE INDEX idx_service_custom_elements_user_id ON service_custom_elements(user_id);

CREATE TABLE service_custom_templates_new (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  text TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

INSERT INTO service_custom_templates_new (id, user_id, title, text, created_at, updated_at)
SELECT id, user_id, title, text, created_at, updated_at
FROM service_custom_templates;

DROP TABLE service_custom_templates;
ALTER TABLE service_custom_templates_new RENAME TO service_custom_templates;

CREATE INDEX idx_service_custom_templates_user_id ON service_custom_templates(user_id);
CREATE INDEX idx_service_custom_templates_updated_at ON service_custom_templates(updated_at);

COMMIT;
PRAGMA foreign_keys = ON;
