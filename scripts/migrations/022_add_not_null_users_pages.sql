PRAGMA foreign_keys=OFF;
BEGIN;

DELETE FROM pages WHERE slug IS NULL;
DELETE FROM users WHERE email IS NULL;
DELETE FROM services WHERE user_id NOT IN (SELECT id FROM users);

CREATE TABLE pages_new (
  id INTEGER PRIMARY KEY,
  title TEXT,
  content TEXT,
  slug TEXT NOT NULL
);

INSERT INTO pages_new (id, title, content, slug)
SELECT id, title, content, slug FROM pages;

DROP TABLE pages;
ALTER TABLE pages_new RENAME TO pages;

CREATE UNIQUE INDEX idx_pages_slug ON pages(slug);

CREATE TABLE users_new (
  id INTEGER PRIMARY KEY,
  first_name TEXT,
  last_name TEXT,
  email TEXT NOT NULL,
  password_hash TEXT
);

INSERT INTO users_new (id, first_name, last_name, email, password_hash)
SELECT id, first_name, last_name, email, password_hash FROM users;

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;

CREATE UNIQUE INDEX idx_users_email ON users(email);

COMMIT;
PRAGMA foreign_keys=ON;
