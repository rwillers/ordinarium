-- Superseded by 013_force_fix_collect_newlines.sql; kept for history.
UPDATE "texts"
SET "data" = json_set(
  "data",
  '$.text',
  replace(json_extract("data", '$.text'), '\\n', char(10))
)
WHERE "id" IN (74, 1268)
  AND json_extract("data", '$.text') LIKE '%\\n%';
