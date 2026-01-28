ALTER TABLE users
ADD COLUMN feature_flags TEXT CHECK (feature_flags IS NULL OR json_valid(feature_flags));
