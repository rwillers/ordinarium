UPDATE "texts"
SET "data" = json_set(
  "data",
  '$.text',
  "*A psalm, hymn, or anthem may follow each reading.*\n\n**{{ psalm_reference }}**\n\n*At the end of the psalm the Gloria Patri (Glory be...) may be sung or said*\n\n    Glory be to the Father, and to the Son, and to the Holy Spirit; *\n        as it was in the beginning, is now, and ever shall be,\n        world without end. Amen."
)
WHERE "id" IN (76, 1270);
