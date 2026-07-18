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

CREATE TRIGGER sync_id_sequence_users AFTER INSERT ON users
WHEN NEW.id >= (SELECT next_value FROM id_sequences WHERE name='users')
BEGIN
  UPDATE id_sequences SET next_value=NEW.id + 1 WHERE name='users';
END;
CREATE TRIGGER sync_id_sequence_services AFTER INSERT ON services
WHEN NEW.id >= (SELECT next_value FROM id_sequences WHERE name='services')
BEGIN
  UPDATE id_sequences SET next_value=NEW.id + 1 WHERE name='services';
END;
CREATE TRIGGER sync_id_sequence_service_shares AFTER INSERT ON service_shares
WHEN NEW.id >= (SELECT next_value FROM id_sequences WHERE name='service_shares')
BEGIN
  UPDATE id_sequences SET next_value=NEW.id + 1 WHERE name='service_shares';
END;
CREATE TRIGGER sync_id_sequence_service_custom_elements AFTER INSERT ON service_custom_elements
WHEN NEW.id >= (SELECT next_value FROM id_sequences WHERE name='service_custom_elements')
BEGIN
  UPDATE id_sequences SET next_value=NEW.id + 1 WHERE name='service_custom_elements';
END;
CREATE TRIGGER sync_id_sequence_service_custom_templates AFTER INSERT ON service_custom_templates
WHEN NEW.id >= (SELECT next_value FROM id_sequences WHERE name='service_custom_templates')
BEGIN
  UPDATE id_sequences SET next_value=NEW.id + 1 WHERE name='service_custom_templates';
END;
CREATE TRIGGER sync_id_sequence_service_pco_links AFTER INSERT ON service_pco_links
WHEN NEW.id >= (SELECT next_value FROM id_sequences WHERE name='service_pco_links')
BEGIN
  UPDATE id_sequences SET next_value=NEW.id + 1 WHERE name='service_pco_links';
END;
CREATE TRIGGER sync_id_sequence_service_pco_item_links AFTER INSERT ON service_pco_item_links
WHEN NEW.id >= (SELECT next_value FROM id_sequences WHERE name='service_pco_item_links')
BEGIN
  UPDATE id_sequences SET next_value=NEW.id + 1 WHERE name='service_pco_item_links';
END;
