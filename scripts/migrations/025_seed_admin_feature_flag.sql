UPDATE users
SET feature_flags = json_set(coalesce(feature_flags, '{}'), '$.admin', true)
WHERE id = 1;
