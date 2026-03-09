ALTER TABLE users ADD COLUMN last_accessed_at TEXT;

UPDATE users
SET last_accessed_at = last_login_at
WHERE last_accessed_at IS NULL
  AND last_login_at IS NOT NULL;
