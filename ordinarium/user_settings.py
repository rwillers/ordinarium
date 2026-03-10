import re

from .service_defaults import DEFAULT_RITE

DEFAULT_BIBLE_TRANSLATION = "ESV"
DEFAULT_SERVICE_TIME = "10:00"
BIBLE_TRANSLATION_OPTIONS = ("ESV", "NRSV", "NIV")
GREETING_RESPONSE_OPTIONS = ("with_your_spirit", "also_with_you")
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def resolve_default_rite(value, rite_options=None):
    normalized = (value or "").strip()
    if rite_options:
        if normalized in rite_options:
            return normalized
        if DEFAULT_RITE in rite_options:
            return DEFAULT_RITE
        return rite_options[0]
    return normalized or DEFAULT_RITE


def resolve_default_bible_translation(value):
    normalized = (value or "").strip().upper()
    if normalized in BIBLE_TRANSLATION_OPTIONS:
        return normalized
    return DEFAULT_BIBLE_TRANSLATION


def resolve_default_service_time(value):
    normalized = (value or "").strip()
    if TIME_PATTERN.match(normalized):
        return normalized
    return DEFAULT_SERVICE_TIME


def resolve_greeting_response_form(value):
    normalized = (value or "").strip()
    if normalized in GREETING_RESPONSE_OPTIONS:
        return normalized
    return "with_your_spirit"


def resolve_user_settings(user, rite_options=None):
    return {
        "default_rite": resolve_default_rite(
            read_user_setting(user, "default_rite"), rite_options
        ),
        "default_bible_translation": resolve_default_bible_translation(
            read_user_setting(user, "default_bible_translation")
        ),
        "default_service_time": resolve_default_service_time(
            read_user_setting(user, "default_service_time")
        ),
        "greeting_response_form": resolve_greeting_response_form(
            read_user_setting(user, "greeting_response_form")
        ),
    }


def validate_user_settings(
    default_rite,
    default_bible_translation,
    default_service_time,
    greeting_response_form,
    rite_options,
):
    normalized_rite = (default_rite or "").strip()
    if normalized_rite not in rite_options:
        return None, "Default rite is invalid."

    normalized_translation = (default_bible_translation or "").strip().upper()
    if normalized_translation not in BIBLE_TRANSLATION_OPTIONS:
        return None, "Default Bible translation is invalid."

    normalized_time = (default_service_time or "").strip()
    if not TIME_PATTERN.match(normalized_time):
        return None, "Default service time must be a valid 24-hour time."

    normalized_greeting_response = (greeting_response_form or "").strip()
    if normalized_greeting_response not in GREETING_RESPONSE_OPTIONS:
        return None, "Greeting response preference is invalid."

    return (
        {
            "default_rite": normalized_rite,
            "default_bible_translation": normalized_translation,
            "default_service_time": normalized_time,
            "greeting_response_form": normalized_greeting_response,
        },
        None,
    )


def read_user_setting(user, key):
    if user is None:
        return None
    if isinstance(user, dict):
        return user.get(key)
    if hasattr(user, key):
        return getattr(user, key)
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    return None
