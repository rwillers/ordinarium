PRAGMA foreign_keys=OFF;
BEGIN;

DELETE FROM services
WHERE user_id IS NULL
  OR user_id NOT IN (SELECT id FROM users);

DELETE FROM service_shares
WHERE service_id NOT IN (SELECT id FROM services);

WITH ranked AS (
  SELECT
    id,
    ROW_NUMBER() OVER (
      PARTITION BY service_id
      ORDER BY created_at DESC, id DESC
    ) AS rn
  FROM service_shares
)
DELETE FROM service_shares
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

CREATE TABLE services_new (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  title TEXT,
  rite TEXT,
  text_order TEXT,
  text_disabled TEXT,
  season TEXT,
  service_date TEXT,
  observance_handle TEXT,
  lesson_overrides JSON,
  offertory_sentence_id INTEGER,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

INSERT INTO services_new (
  id,
  user_id,
  title,
  rite,
  text_order,
  text_disabled,
  season,
  service_date,
  observance_handle,
  lesson_overrides,
  offertory_sentence_id
)
SELECT
  id,
  user_id,
  title,
  rite,
  text_order,
  text_disabled,
  season,
  service_date,
  observance_handle,
  lesson_overrides,
  offertory_sentence_id
FROM services;

DROP TABLE services;
ALTER TABLE services_new RENAME TO services;

CREATE INDEX idx_services_user_id ON services(user_id);
CREATE INDEX idx_services_rite ON services(rite);
CREATE INDEX idx_services_season ON services(season);
CREATE INDEX idx_services_service_date ON services(service_date);
CREATE INDEX idx_services_user_id_service_date ON services(user_id, service_date);

DROP INDEX IF EXISTS idx_service_shares_service_id;
CREATE UNIQUE INDEX idx_service_shares_service_id ON service_shares(service_id);

DROP INDEX IF EXISTS idx_pages_slug;
CREATE UNIQUE INDEX idx_pages_slug ON pages(slug);

DROP INDEX IF EXISTS idx_users_email;
CREATE UNIQUE INDEX idx_users_email ON users(email);

CREATE INDEX idx_texts_lookup
  ON texts(type, filter_type, filter_content, default_order);

COMMIT;
PRAGMA foreign_keys=ON;
