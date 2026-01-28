alter table services add column updated_at text;
update services set updated_at = CURRENT_TIMESTAMP where updated_at is null;
