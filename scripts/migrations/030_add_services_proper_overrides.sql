alter table services add column proper_overrides json check (proper_overrides is null or json_valid(proper_overrides));
