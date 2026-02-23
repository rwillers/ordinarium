SERVICE_OPTION_DEFINITIONS = {
    "lords_prayer.form": {
        "label": "Lord's Prayer form",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {
                "value": "traditional",
                "label": "Traditional language (Our Father, who art in heaven)",
            },
            {
                "value": "contemporary",
                "label": "Contemporary language (Our Father in heaven)",
            },
        ],
    },
    "dismissal.form": {
        "label": "Dismissal form",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {
                "value": "go_forth_name_of_christ",
                "label": "Let us go forth in the Name of Christ",
            },
            {
                "value": "go_in_peace_love_serve",
                "label": "Go in peace to love and serve the Lord",
            },
            {
                "value": "go_forth_rejoicing",
                "label": "Let us go forth into the world, rejoicing in the power of the Holy Spirit",
            },
            {
                "value": "let_us_bless",
                "label": "Let us bless the Lord",
            },
        ],
    },
    "fraction.alleluia_mode": {
        "label": "Fraction alleluia mode",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "auto", "label": "Auto by season"},
            {"value": "on", "label": "Always include alleluia"},
            {"value": "off", "label": "Always omit alleluia"},
        ],
    },
    "dismissal.alleluia_mode": {
        "label": "Dismissal alleluia mode",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "auto", "label": "Auto by season"},
            {"value": "on", "label": "Always include alleluia"},
            {"value": "off", "label": "Always omit alleluia"},
        ],
    },
    "confession.invitation_form": {
        "label": "Confession invitation form",
        "rites": {"Anglican Standard Text"},
        "choices": [
            {"value": "long", "label": "Long invitation"},
            {"value": "short", "label": "Short invitation"},
        ],
    },
}


def _is_rite_allowed(definition, rite):
    allowed = definition.get("rites") or set()
    return not allowed or rite in allowed


def normalize_service_option_value(value):
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def is_valid_service_option_value(rite, option_key, option_value):
    definition = SERVICE_OPTION_DEFINITIONS.get(option_key)
    if not definition:
        return False
    if not _is_rite_allowed(definition, rite):
        return False
    if option_value is None:
        return True
    valid_values = {choice["value"] for choice in definition.get("choices") or []}
    return option_value in valid_values


def get_service_option_definitions_for_rite(rite):
    output = {}
    for key, definition in SERVICE_OPTION_DEFINITIONS.items():
        if not _is_rite_allowed(definition, rite):
            continue
        output[key] = {
            "label": definition.get("label") or key,
            "choices": list(definition.get("choices") or []),
        }
    return output
