ALTER TABLE users
ADD COLUMN default_rite TEXT NOT NULL DEFAULT 'Renewed Ancient Text';

ALTER TABLE users
ADD COLUMN default_bible_translation TEXT NOT NULL DEFAULT 'ESV';

ALTER TABLE users
ADD COLUMN default_service_time TEXT NOT NULL DEFAULT '10:00';
