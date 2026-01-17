update texts
set data = json_set(
	data,
	'$.text',
	replace(
		replace(json_extract(data, '$.text'), '<span class="trailing-indent">', ''),
		'</span>',
		''
	)
)
where json_extract(data, '$.text') like '%trailing-indent%';
