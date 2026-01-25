from datetime import date

from .liturgical_calendar import resolve_observance


def format_services(services):
    formatted = []
    for service in services:
        display_date = service["service_date"]
        try:
            parsed = date.fromisoformat(service["service_date"])
            display_date = f"{parsed.month}/{parsed.day}/{parsed.year}"
        except (TypeError, ValueError):
            pass
        title = None
        observance_handle = service["observance_handle"]
        if service["service_date"]:
            try:
                observance = resolve_observance(
                    date.fromisoformat(service["service_date"]),
                    observance_handle,
                )
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
                "rite": service["rite"],
            }
        )
    return formatted
