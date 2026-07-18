CREATE TABLE id_sequences (
  name TEXT PRIMARY KEY,
  next_value INTEGER NOT NULL CHECK (next_value > 0)
);

INSERT INTO id_sequences (name, next_value)
SELECT 'users', COALESCE(MAX(id), 0) + 1 FROM users;
INSERT INTO id_sequences (name, next_value)
SELECT 'services', COALESCE(MAX(id), 0) + 1 FROM services;
INSERT INTO id_sequences (name, next_value)
SELECT 'service_shares', COALESCE(MAX(id), 0) + 1 FROM service_shares;
INSERT INTO id_sequences (name, next_value)
SELECT 'service_custom_elements', COALESCE(MAX(id), 0) + 1 FROM service_custom_elements;
INSERT INTO id_sequences (name, next_value)
SELECT 'service_custom_templates', COALESCE(MAX(id), 0) + 1 FROM service_custom_templates;
INSERT INTO id_sequences (name, next_value)
SELECT 'service_pco_links', COALESCE(MAX(id), 0) + 1 FROM service_pco_links;
INSERT INTO id_sequences (name, next_value)
SELECT 'service_pco_item_links', COALESCE(MAX(id), 0) + 1 FROM service_pco_item_links;
