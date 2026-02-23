import json


SERVICE_OPTION_DEFINITIONS = {
    "law.form": {
        "label": "Summary of the Law form",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "summary", "label": "Use Summary of the Law"},
            {"value": "decalogue", "label": "Use Decalogue (page 100)"},
        ],
    },
    "penitential_song.mode": {
        "label": "Penitential song mode",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "kyrie", "label": "Use Kyrie"},
            {"value": "trisagion", "label": "Use Trisagion"},
        ],
    },
    "kyrie.form": {
        "label": "Kyrie form",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "traditional", "label": "Lord, have mercy upon us"},
            {"value": "contemporary", "label": "Lord, have mercy"},
            {"value": "greek", "label": "Kyrie eleison"},
        ],
    },
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
    "creed.filioque_clause": {
        "label": "Filioque clause",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "include", "label": "Include “and the Son”"},
            {"value": "omit", "label": "Omit “and the Son”"},
        ],
    },
    "comfortable_words.sentences": {
        "label": "Comfortable Words sentences",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "input_type": "multi_select",
        "choices": [
            {"value": "matthew_11_28", "label": "Matthew 11:28"},
            {"value": "john_3_16", "label": "John 3:16"},
            {"value": "first_timothy_1_15", "label": "1 Timothy 1:15"},
            {"value": "first_john_2_1_2", "label": "1 John 2:1-2"},
        ],
    },
    "prayers.public_service.especially_clause": {
        "label": "Prayers public service clause",
        "rites": {"Renewed Ancient Text"},
        "choices": [
            {"value": "include", "label": "Include bracketed clause"},
            {"value": "omit", "label": "Omit bracketed clause"},
        ],
    },
    "prayers.public_service.especially_names": {
        "label": "Prayers public service names",
        "rites": {"Renewed Ancient Text"},
        "input_type": "text",
        "placeholder": "e.g., our mayor and city council",
        "max_length": 160,
    },
    "prayers.adversity.especially_clause": {
        "label": "Prayers adversity clause",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "include", "label": "Include bracketed clause"},
            {"value": "omit", "label": "Omit bracketed clause"},
        ],
    },
    "prayers.adversity.especially_names": {
        "label": "Prayers adversity names",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "input_type": "text",
        "placeholder": "e.g., those suffering from illness",
        "max_length": 160,
    },
    "prayers.departed.especially_clause": {
        "label": "Prayers departed clause",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "include", "label": "Include bracketed clause"},
            {"value": "omit", "label": "Omit bracketed clause"},
        ],
    },
    "prayers.departed.especially_names": {
        "label": "Prayers departed names",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "input_type": "text",
        "placeholder": "e.g., N., N., and N.",
        "max_length": 160,
    },
    "prayers.saints.named_insert": {
        "label": "Prayers saints name insert",
        "rites": {"Anglican Standard Text"},
        "choices": [
            {"value": "include", "label": "Include bracketed insert"},
            {"value": "omit", "label": "Omit bracketed insert"},
        ],
    },
    "prayers.saints.named_person": {
        "label": "Prayers saints named person",
        "rites": {"Anglican Standard Text"},
        "input_type": "text",
        "placeholder": "e.g., St. Mary",
        "max_length": 120,
    },
    "prayers.form": {
        "label": "Prayers form",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "rat", "label": "Use Renewed Ancient Text form"},
            {"value": "ast", "label": "Use Anglican Standard Text form"},
        ],
    },
    "prayers.ast.profile": {
        "label": "AST local profile",
        "rites": {"Anglican Standard Text"},
        "choices": [
            {"value": "american", "label": "American context (President / Bishop)"},
            {
                "value": "commonwealth",
                "label": "Commonwealth context (Sovereign / Archbishop)",
            },
        ],
    },
    "prayers.ast.civil_leader.name": {
        "label": "AST civil leader name",
        "rites": {"Anglican Standard Text"},
        "input_type": "text",
        "placeholder": "e.g., Jane Doe",
        "max_length": 120,
    },
    "prayers.ast.civil_leader.title": {
        "label": "AST civil leader title",
        "rites": {"Anglican Standard Text"},
        "choices": [
            {"value": "president", "label": "President"},
            {"value": "sovereign", "label": "Sovereign"},
            {"value": "prime_minister", "label": "Prime Minister"},
        ],
    },
    "prayers.ast.clergy.name": {
        "label": "AST clergy name",
        "rites": {"Anglican Standard Text"},
        "input_type": "text",
        "placeholder": "e.g., Bp. N.",
        "max_length": 120,
    },
    "prayers.ast.clergy.title": {
        "label": "AST clergy title",
        "rites": {"Anglican Standard Text"},
        "choices": [
            {"value": "archbishop", "label": "Archbishop"},
            {"value": "bishop", "label": "Bishop"},
            {"value": "priest", "label": "Priest"},
            {"value": "deacon", "label": "Deacon"},
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
    "fraction.form": {
        "label": "Fraction form",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {
                "value": "passover_is_sacrificed",
                "label": "Christ our Passover is sacrificed for us",
            },
            {
                "value": "passover_lamb_has_been_sacrificed",
                "label": "Christ our Passover Lamb has been sacrificed",
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
    "communion.invitation.form": {
        "label": "Communion invitation form",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {
                "value": "gifts_of_god",
                "label": "The gifts of God for the people of God",
            },
            {
                "value": "behold_lamb",
                "label": "Behold the Lamb of God",
            },
        ],
    },
    "communion.invitation.appended_clause": {
        "label": "Communion invitation appended clause",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "include", "label": "Include appended clause"},
            {"value": "omit", "label": "Omit appended clause"},
        ],
    },
    "communion.invitation.appended_text": {
        "label": "Communion invitation appended text",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "input_type": "text",
        "placeholder": "e.g., Take and eat in remembrance...",
        "max_length": 320,
    },
    "communion.distribution.body_clause": {
        "label": "Body distribution clause",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "include", "label": "Include long formula clause"},
            {"value": "omit", "label": "Omit long formula clause"},
        ],
    },
    "communion.distribution.body_text": {
        "label": "Body distribution text",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "input_type": "text",
        "placeholder": "e.g., which was given for you...",
        "max_length": 500,
    },
    "communion.distribution.blood_clause": {
        "label": "Blood distribution clause",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "include", "label": "Include long formula clause"},
            {"value": "omit", "label": "Omit long formula clause"},
        ],
    },
    "communion.distribution.blood_text": {
        "label": "Blood distribution text",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "input_type": "text",
        "placeholder": "e.g., which was shed for you...",
        "max_length": 500,
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
    "post_communion.form": {
        "label": "Post Communion form",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "own_rite", "label": "Use this rite's prayer"},
            {"value": "other_rite", "label": "Use the other rite's prayer"},
        ],
    },
    "psalm.gloria_patri": {
        "label": "Psalm Gloria Patri",
        "rites": {"Renewed Ancient Text", "Anglican Standard Text"},
        "choices": [
            {"value": "include", "label": "Include Gloria Patri"},
            {"value": "omit", "label": "Omit Gloria Patri"},
        ],
    },
}


def _is_rite_allowed(definition, rite):
    allowed = definition.get("rites") or set()
    return not allowed or rite in allowed


def normalize_service_option_value(option_key, value):
    if value is None:
        return None
    definition = SERVICE_OPTION_DEFINITIONS.get(option_key) or {}
    if definition.get("input_type") == "multi_select":
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            return None
        try:
            parsed = json.loads(normalized)
        except (TypeError, ValueError):
            return normalized
        if not isinstance(parsed, list):
            return normalized
        output = []
        seen = set()
        for item in parsed:
            if not isinstance(item, str):
                return normalized
            cleaned = item.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            output.append(cleaned)
        return output or None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if definition.get("input_type") == "text":
        normalized = " ".join(normalized.split())
    return normalized or None


def is_valid_service_option_value(rite, option_key, option_value):
    definition = SERVICE_OPTION_DEFINITIONS.get(option_key)
    if not definition:
        return False
    if not _is_rite_allowed(definition, rite):
        return False
    if option_value is None:
        return True
    if definition.get("input_type") == "multi_select":
        if not isinstance(option_value, list):
            return False
        valid_values = {choice["value"] for choice in definition.get("choices") or []}
        if not option_value:
            return False
        return all(
            isinstance(value, str) and value in valid_values for value in option_value
        )
    if definition.get("input_type") == "text":
        max_length = definition.get("max_length") or 200
        return isinstance(option_value, str) and len(option_value) <= max_length
    valid_values = {choice["value"] for choice in definition.get("choices") or []}
    return option_value in valid_values


def get_service_option_definitions_for_rite(rite):
    output = {}
    for key, definition in SERVICE_OPTION_DEFINITIONS.items():
        if not _is_rite_allowed(definition, rite):
            continue
        output[key] = {
            "label": definition.get("label") or key,
            "input_type": definition.get("input_type") or "select",
            "placeholder": definition.get("placeholder") or "",
            "max_length": definition.get("max_length") or 0,
            "choices": list(definition.get("choices") or []),
        }
    return output
