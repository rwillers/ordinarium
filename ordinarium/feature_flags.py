from .plan_tokens import parse_json_object

FEATURE_ADMIN = "admin"
FEATURE_PCO_SYNC = "pco_sync"
FEATURE_LABELS = {
    FEATURE_ADMIN: "Admin access",
    FEATURE_PCO_SYNC: "PCO sync",
}


def parse_feature_flags(value):
    flags = parse_json_object(value)
    if not isinstance(flags, dict):
        return {}
    return {str(key): bool(value) for key, value in flags.items()}


def user_has_feature(user, feature):
    if not user:
        return False
    flags = getattr(user, "feature_flags", None)
    if not isinstance(flags, dict):
        return False
    return bool(flags.get(feature))


def list_feature_flags():
    return [{"key": key, "label": label} for key, label in FEATURE_LABELS.items()]
