ALTER TABLE users ADD COLUMN created_at TEXT;
ALTER TABLE users ADD COLUMN last_login_at TEXT;

UPDATE users
SET created_at = CURRENT_TIMESTAMP
WHERE created_at IS NULL;
