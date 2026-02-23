alter table services add column service_option_values json check (service_option_values is null or json_valid(service_option_values)) default '{}';
