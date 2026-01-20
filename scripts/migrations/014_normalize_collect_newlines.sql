-- Normalize any literal \n sequences (single or double-escaped) in Collect text.
UPDATE "texts"
SET "data" = json_set(
  "data",
  '$.text',
  replace(
    replace(json_extract("data", '$.text'), '\\\\n', char(10)),
    '\\n',
    char(10)
  )
)
WHERE "id" IN (74, 1268);
