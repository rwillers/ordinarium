UPDATE "texts"
SET "data" = json_set(
  "data",
  '$.text',
  "*The Celebrant says to the People*\n\n*&nbsp;* The Lord be with you.  \n*People* **And with your spirit.**  \n*Officiant* Let us pray.\n\n*The Celebrant prays the Collect.*\n\n{{ collect_of_the_day | markdown }}"
)
WHERE "id" IN (74, 1268);
