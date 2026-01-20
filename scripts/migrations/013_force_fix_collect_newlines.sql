UPDATE "texts"
SET "data" = json_set(
  "data",
  '$.text',
  replace(json_extract("data", '$.text'), '\\n', char(10))
)
WHERE "id" IN (74, 1268);
