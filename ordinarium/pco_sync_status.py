from datetime import datetime


def parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def resolve_pco_sync_state(service_updated_at, last_synced_at, last_sync_status):
    if last_sync_status == "failed":
        return "failed"
    if not last_synced_at:
        return "unsynced"
    service_dt = parse_timestamp(service_updated_at)
    sync_dt = parse_timestamp(last_synced_at)
    if service_dt and sync_dt and service_dt > sync_dt:
        return "unsynced"
    return "synced"
