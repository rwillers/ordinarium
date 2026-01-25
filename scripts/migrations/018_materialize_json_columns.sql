PRAGMA foreign_keys=OFF;

CREATE TABLE pages_new (
  id INTEGER PRIMARY KEY,
  title TEXT,
  content TEXT,
  slug TEXT
);
INSERT INTO pages_new (id, title, content, slug)
SELECT
  id,
  json_extract(data, '$.title'),
  json_extract(data, '$.content'),
  json_extract(data, '$.slug')
FROM pages;
DROP TABLE pages;
ALTER TABLE pages_new RENAME TO pages;
CREATE INDEX idx_pages_slug ON pages(slug);

CREATE TABLE services_new (
  id INTEGER PRIMARY KEY,
  user_id INTEGER,
  title TEXT,
  rite TEXT,
  text_order TEXT,
  text_disabled TEXT,
  season TEXT,
  service_date TEXT,
  observance_handle TEXT,
  lesson_overrides JSON,
  offertory_sentence_id INTEGER
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
  json_extract(data, '$.user_id'),
  json_extract(data, '$.title'),
  json_extract(data, '$.rite'),
  json_extract(data, '$.text_order'),
  json_extract(data, '$.text_disabled'),
  json_extract(data, '$.season'),
  json_extract(data, '$.service_date'),
  json_extract(data, '$.observance_handle'),
  json_extract(data, '$.lesson_overrides'),
  json_extract(data, '$.offertory_sentence_id')
FROM services;
DROP TABLE services;
ALTER TABLE services_new RENAME TO services;
CREATE INDEX idx_services_user_id ON services(user_id);
CREATE INDEX idx_services_rite ON services(rite);
CREATE INDEX idx_services_season ON services(season);
CREATE INDEX idx_services_service_date ON services(service_date);

CREATE TABLE users_new (
  id INTEGER PRIMARY KEY,
  first_name TEXT,
  last_name TEXT,
  email TEXT,
  password_hash TEXT
);
INSERT INTO users_new (id, first_name, last_name, email, password_hash)
SELECT
  id,
  json_extract(data, '$.first_name'),
  json_extract(data, '$.last_name'),
  json_extract(data, '$.email'),
  json_extract(data, '$.password_hash')
FROM users;
DROP TABLE users;
ALTER TABLE users_new RENAME TO users;
CREATE INDEX idx_users_email ON users(email);

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
  subcycles JSON
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
  json_extract(data, '$.type'),
  json_extract(data, '$.filter.type'),
  json_extract(data, '$.filter.content'),
  json_extract(data, '$.text'),
  json_extract(data, '$.title'),
  json_extract(data, '$.default_order'),
  json_extract(data, '$.detailed_title'),
  json_extract(data, '$.reading'),
  json_extract(data, '$.option_group'),
  json_extract(data, '$.optional'),
  json_extract(data, '$.book'),
  json_extract(data, '$.book_name'),
  json_extract(data, '$.reference_long'),
  json_extract(data, '$.reference_short'),
  json_extract(data, '$.note'),
  json_extract(data, '$.subcycles')
FROM texts;
DROP TABLE texts;
ALTER TABLE texts_new RENAME TO texts;
CREATE INDEX idx_texts_type on texts(type);
CREATE INDEX idx_texts_filter_type on texts(filter_type);
CREATE INDEX idx_texts_filter_content on texts(filter_content);

PRAGMA foreign_keys=ON;
