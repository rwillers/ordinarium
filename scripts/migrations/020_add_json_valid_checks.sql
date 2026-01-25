PRAGMA foreign_keys=OFF;
BEGIN;

UPDATE services SET text_order=NULL WHERE text_order='';
UPDATE services SET text_disabled=NULL WHERE text_disabled='';
UPDATE services SET lesson_overrides=NULL WHERE lesson_overrides='';
UPDATE texts SET subcycles=NULL WHERE subcycles='';

CREATE TABLE services_new (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  title TEXT,
  rite TEXT,
  text_order TEXT CHECK (text_order IS NULL OR json_valid(text_order)),
  text_disabled TEXT CHECK (text_disabled IS NULL OR json_valid(text_disabled)),
  season TEXT,
  service_date TEXT,
  observance_handle TEXT,
  lesson_overrides JSON CHECK (lesson_overrides IS NULL OR json_valid(lesson_overrides)),
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

CREATE TABLE texts_new (
  id INTEGER PRIMARY KEY,
  type TEXT,
  filter_type TEXT,
  filter_content TEXT,
  text TEXT,
  title TEXT,
  default_order INTEGER,
  detailed_title TEXT,
  reading INTEGER,
  option_group TEXT,
  optional INTEGER,
  book TEXT,
  book_name TEXT,
  reference_long TEXT,
  reference_short TEXT,
  note TEXT,
  subcycles JSON CHECK (subcycles IS NULL OR json_valid(subcycles))
);

INSERT INTO texts_new (
  id,
  type,
  filter_type,
  filter_content,
  text,
  title,
  default_order,
  detailed_title,
  reading,
  option_group,
  optional,
  book,
  book_name,
  reference_long,
  reference_short,
  note,
  subcycles
)
SELECT
  id,
  type,
  filter_type,
  filter_content,
  text,
  title,
  default_order,
  detailed_title,
  reading,
  option_group,
  optional,
  book,
  book_name,
  reference_long,
  reference_short,
  note,
  subcycles
FROM texts;

DROP TABLE texts;
ALTER TABLE texts_new RENAME TO texts;

CREATE INDEX idx_texts_lookup
  ON texts(type, filter_type, filter_content, default_order);

COMMIT;
PRAGMA foreign_keys=ON;
