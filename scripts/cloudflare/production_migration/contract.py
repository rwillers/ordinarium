"""Fail-closed data contract for the production SQLite-to-D1 cutover."""

CONTRACT_VERSION = 1

MIGRATED_TABLES = (
    "users",
    "services",
    "pco_connections",
    "service_pco_links",
    "service_pco_item_links",
    "pco_batch_sync_jobs",
    "pco_plan_operations",
    "pco_batch_sync_rows",
    "service_shares",
    "service_custom_elements",
    "service_custom_templates",
    "user_text_overrides",
)

REFERENCE_TABLES = {
    "fragments",
    "holidays",
    "pages",
    "subcycles",
    "texts",
}

TRANSIENT_TABLES = {
    "password_reset_requests",
    "pco_rate_limit_windows",
    "pco_service_sync_leases",
}

INFRASTRUCTURE_TABLES = {
    "id_sequences",
    "schema_migrations",
    "texts_import",
}

LEGACY_TABLES = {"password_reset_tokens"}

KNOWN_SOURCE_TABLES = (
    set(MIGRATED_TABLES)
    | REFERENCE_TABLES
    | TRANSIENT_TABLES
    | INFRASTRUCTURE_TABLES
    | LEGACY_TABLES
)

SEQUENCE_TABLES = (
    "users",
    "services",
    "service_shares",
    "service_custom_elements",
    "service_custom_templates",
    "service_pco_links",
    "service_pco_item_links",
)

TERMINAL_STATUSES = {
    "pco_batch_sync_jobs": {"succeeded", "failed"},
    "pco_plan_operations": {"completed", "failed"},
    "pco_batch_sync_rows": {"success", "failed", "skipped"},
}

CLAIM_COLUMNS = {
    "pco_connections": ("refresh_claim_token", "refresh_claim_expires_at"),
    "pco_batch_sync_jobs": ("claim_token", "claim_expires_at"),
    "pco_plan_operations": ("claim_token", "claim_expires_at"),
    "pco_batch_sync_rows": ("claim_token", "claim_expires_at"),
}

EXCLUSION_REASONS = {
    "password_reset_requests": (
        "In-flight reset links are invalidated at cutover; users can request new links."
    ),
    "pco_rate_limit_windows": "Rate-limit windows are ephemeral and restart empty.",
    "pco_service_sync_leases": "Synchronization leases are ephemeral and restart empty.",
}
