-- Force exact Collect text with literal newlines to avoid escaped \n issues.
UPDATE "texts"
SET "data" = json_set(
  "data",
  '$.text',
  '*The Celebrant says to the People*'
  || char(10) || char(10)
  || '*&nbsp;* The Lord be with you.  '
  || char(10)
  || '*People* **And with your spirit.**  '
  || char(10)
  || '*Officiant* Let us pray.'
  || char(10) || char(10)
  || '*The Celebrant prays the Collect.*'
  || char(10) || char(10)
  || '{{ collect_of_the_day | markdown }}'
)
WHERE "id" IN (74, 1268);
