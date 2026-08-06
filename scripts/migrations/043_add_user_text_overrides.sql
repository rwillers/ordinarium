CREATE TABLE user_text_overrides (
  user_id INTEGER NOT NULL,
  text_id INTEGER NOT NULL,
  replacement_text TEXT NOT NULL,
  base_text_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, text_id),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(text_id) REFERENCES texts(id) ON DELETE CASCADE
);

CREATE INDEX idx_user_text_overrides_text_id
  ON user_text_overrides(text_id);
