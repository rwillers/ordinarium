from datetime import date

from .liturgical_calendar import resolve_observance


def format_services(services):
    formatted = []
    for service in services:
        display_date = service["service_date"]
        parsed_date = None
        try:
            parsed_date = date.fromisoformat(service["service_date"])
            display_date = f"{parsed_date.month}/{parsed_date.day}/{parsed_date.year}"
        except (TypeError, ValueError):
            pass
        title = None
        observance_handle = service["observance_handle"]
        if service["service_date"] and parsed_date:
            try:
                observance = resolve_observance(parsed_date, observance_handle)
            except ValueError:
                observance = None
            if observance:
                title = observance.name or observance.alternative_name
        if not title:
            title = service["title"]
        formatted.append(
            {
                "id": service["id"],
                "title": title or "Untitled Service",
                "service_date": service["service_date"],
                "display_date": display_date,
                "season": service["season"],
                "rite": service["rite"],
            }
        )
    return formatted
