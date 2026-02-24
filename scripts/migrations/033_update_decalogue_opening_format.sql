UPDATE texts
SET text = replace(
  text,
  '*Celebrant* God spoke these words and said:

I am the Lord your God.  
You shall have no other gods but me.  
*People* **Lord, have mercy upon us, and incline our hearts to keep this law.**',
  '*Celebrant* God spoke these words and said: I am the Lord your God. You shall have no other gods but me.  
*People* **Lord, have mercy upon us, and incline our hearts to keep this law.**'
)
WHERE type='law_form'
  AND filter_type='rite'
  AND filter_content IN ('Renewed Ancient Text', 'Anglican Standard Text');
