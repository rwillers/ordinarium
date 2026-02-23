import re


EASTER_ALLELUIA_SEASONS = {"Easter", "Ascension", "Pentecost"}


def apply_service_option_overrides(ordinaries, service_option_values, season=None):
    if not isinstance(ordinaries, list) or not ordinaries:
        return ordinaries
    if not isinstance(service_option_values, dict) or not service_option_values:
        return ordinaries

    updated = []
    for item in ordinaries:
        output = dict(item)
        if output.get("type") == "custom":
            updated.append(output)
            continue
        title = _normalize_title(output.get("title"))
        text = output.get("text") or ""
        if title == "the lord's prayer":
            text = _apply_lords_prayer_form(text, service_option_values)
        elif title == "the nicene creed":
            text = _apply_creed_filioque_clause(text, service_option_values)
        elif title == "the prayers of the people":
            text = _apply_prayers_bracket_clauses(text, service_option_values)
        elif title == "the confession and absolution of sin":
            text = _apply_confession_invitation_form(text, service_option_values)
        elif title == "the fraction":
            text = _apply_fraction_form(text, service_option_values)
            text = _apply_fraction_alleluia_mode(text, service_option_values, season)
        elif title == "the ministration of communion":
            text = _apply_communion_invitation_form(text, service_option_values)
            text = _apply_communion_clauses(text, service_option_values)
        elif title == "the dismissal":
            text = _apply_dismissal_form(text, service_option_values)
            text = _apply_dismissal_alleluia_mode(text, service_option_values, season)
        output["text"] = text
        updated.append(output)
    return updated


def _normalize_title(value):
    cleaned = (value or "").replace("’", "'")
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def _apply_lords_prayer_form(text, service_option_values):
    form = service_option_values.get("lords_prayer.form")
    if form not in {"traditional", "contemporary"}:
        return text

    pattern = re.compile(
        r"(?s)(.*?\*Celebrant and People together pray\*\n\n)- ```(.*?)```\n- ```(.*?)```(.*)"
    )
    match = pattern.fullmatch(text or "")
    if not match:
        return text

    selected = match.group(2) if form == "traditional" else match.group(3)
    return f"{match.group(1)}- ```{selected}```{match.group(4)}"


def _apply_confession_invitation_form(text, service_option_values):
    form = service_option_values.get("confession.invitation_form")
    if form not in {"long", "short"}:
        return text

    pattern = re.compile(
        r"(?s)(\*The Deacon or other person appointed says the following\*\n\n)"
        r"(.+?)\n\n\*or\*\n\n(.+?)\n\n(\*Silence\*\n\n.*)"
    )
    match = pattern.fullmatch(text or "")
    if not match:
        return text

    selected = match.group(2) if form == "long" else match.group(3)
    return f"{match.group(1)}{selected}\n\n{match.group(4)}"


def _apply_creed_filioque_clause(text, service_option_values):
    mode = service_option_values.get("creed.filioque_clause")
    if mode == "include":
        return re.sub(r"\[and the Son\]", "and the Son", text or "")
    if mode == "omit":
        return re.sub(r"\s*\[and the Son\]", "", text or "")
    return text


def _apply_prayers_bracket_clauses(text, service_option_values):
    output = text or ""
    output = _apply_prayers_named_value_for_prefixes(
        output,
        service_option_values,
        "prayers.public_service.especially_names",
        [
            "For our nation, for those in authority, and for all in public service",
        ],
    )
    output = _apply_prayers_named_value_for_prefixes(
        output,
        service_option_values,
        "prayers.adversity.especially_names",
        [
            "For all those who are in trouble, sorrow, need, sickness, or any other adversity",
            "We ask you in your goodness, O Lord, to comfort and sustain all who in this transitory life are in trouble, sorrow, need, sickness, or any other adversity",
        ],
    )
    output = _apply_prayers_named_value_for_prefixes(
        output,
        service_option_values,
        "prayers.departed.especially_names",
        [
            "For all those who have departed this life in the certain hope of the resurrection,",
            "We remember before you all your servants who have departed this life in your faith and fear,",
        ],
        trailing=",",
    )
    output = _apply_prayers_named_saints_insert_for_prefixes(
        output,
        service_option_values,
        [
            "and we ask you to give us grace to follow the good examples of",
        ],
    )

    output = _apply_bracket_clause_mode_for_prefixes(
        output,
        _resolve_include_omit_mode(
            service_option_values,
            "prayers.public_service.especially_clause",
            "prayers.public_service.especially_names",
        ),
        [
            "For our nation, for those in authority, and for all in public service",
        ],
    )
    output = _apply_bracket_clause_mode_for_prefixes(
        output,
        _resolve_include_omit_mode(
            service_option_values,
            "prayers.adversity.especially_clause",
            "prayers.adversity.especially_names",
        ),
        [
            "For all those who are in trouble, sorrow, need, sickness, or any other adversity",
            "We ask you in your goodness, O Lord, to comfort and sustain all who in this transitory life are in trouble, sorrow, need, sickness, or any other adversity",
        ],
    )
    output = _apply_bracket_clause_mode_for_prefixes(
        output,
        _resolve_include_omit_mode(
            service_option_values,
            "prayers.departed.especially_clause",
            "prayers.departed.especially_names",
        ),
        [
            "For all those who have departed this life in the certain hope of the resurrection,",
            "We remember before you all your servants who have departed this life in your faith and fear,",
        ],
    )
    output = _apply_bracket_clause_mode_for_prefixes(
        output,
        _resolve_include_omit_mode(
            service_option_values,
            "prayers.saints.named_insert",
            "prayers.saints.named_person",
        ),
        [
            "and we ask you to give us grace to follow the good examples of",
        ],
    )
    return output


def _apply_dismissal_form(text, service_option_values):
    form = service_option_values.get("dismissal.form")
    option_map = {
        "go_forth_name_of_christ": 2,
        "go_in_peace_love_serve": 3,
        "go_forth_rejoicing": 4,
        "let_us_bless": 5,
    }
    selected_group = option_map.get(form)
    if not selected_group:
        return text

    pattern = re.compile(
        r"(?s)(\*The Deacon, or the Priest, may dismiss the People with these words\*\n\n)"
        r"(.+?)\n\n\*or this\*\n\n(.+?)\n\n\*or this\*\n\n(.+?)\n\n\*or this\*\n\n(.+?)"
        r"(\n\n\*From the Easter Vigil.*)"
    )
    match = pattern.fullmatch(text or "")
    if not match:
        return text

    return f"{match.group(1)}{match.group(selected_group)}{match.group(6)}"


def _apply_fraction_form(text, service_option_values):
    form = service_option_values.get("fraction.form")
    option_map = {
        "passover_is_sacrificed": 2,
        "passover_lamb_has_been_sacrificed": 3,
    }
    selected_group = option_map.get(form)
    if not selected_group:
        return text

    pattern = re.compile(
        r"(?s)(.*?\*Then may be sung or said\*\n\n)(.+?)\n\n\*or this\*\n\n(.+?)"
        r"(\n\n\*In Lent, Alleluia is omitted, and may be omitted at other times except during Easter Season\.\*)"
    )
    match = pattern.fullmatch(text or "")
    if not match:
        return text

    return f"{match.group(1)}{match.group(selected_group)}{match.group(4)}"


def _apply_communion_invitation_form(text, service_option_values):
    form = service_option_values.get("communion.invitation.form")
    option_map = {
        "gifts_of_god": 2,
        "behold_lamb": 3,
    }
    selected_group = option_map.get(form)
    if not selected_group:
        return text

    pattern = re.compile(
        r"(?s)(\*Facing the People, the Celebrant may say the following invitation\*\n\n)"
        r"(.+?)\n\n\*or this\*\n\n(.+?)\n\n"
        r"(\*The Ministers receive the Sacrament in both kinds, and then immediately deliver it to the People\.\*\n\n.*)"
    )
    match = pattern.fullmatch(text or "")
    if not match:
        return text

    return f"{match.group(1)}{match.group(selected_group)}\n\n{match.group(4)}"


def _apply_communion_clauses(text, service_option_values):
    output = text or ""
    output = _apply_bracket_clause_option(
        output,
        "communion.invitation.appended_clause",
        "The gifts of God for the people of God.",
        service_option_values,
    )
    output = _apply_bracket_clause_option(
        output,
        "communion.distribution.body_clause",
        "The Body of our Lord Jesus Christ,",
        service_option_values,
    )
    output = _apply_bracket_clause_option(
        output,
        "communion.distribution.blood_clause",
        "The Blood of our Lord Jesus Christ,",
        service_option_values,
    )
    return output


def _apply_bracket_clause_option(text, key, prefix, service_option_values):
    mode = service_option_values.get(key)
    if mode not in {"include", "omit"}:
        return text
    return _apply_bracket_clause_mode(text, mode, prefix)


def _apply_bracket_clause_mode(text, mode, prefix):
    if mode not in {"include", "omit"}:
        return text
    pattern = re.compile(rf"({re.escape(prefix)}) \[(.+?)\]")
    match = pattern.search(text or "")
    if not match:
        return text
    if mode == "include":
        return pattern.sub(r"\1 \2", text, count=1)
    return pattern.sub(r"\1", text, count=1)


def _apply_bracket_clause_option_for_prefixes(
    text, key, prefixes, service_option_values
):
    mode = service_option_values.get(key)
    return _apply_bracket_clause_mode_for_prefixes(text, mode, prefixes)


def _apply_bracket_clause_mode_for_prefixes(text, mode, prefixes):
    output = text
    for prefix in prefixes:
        updated = _apply_bracket_clause_mode(output, mode, prefix)
        if updated != output:
            return updated
    return output


def _resolve_include_omit_mode(service_option_values, mode_key, text_key):
    mode = service_option_values.get(mode_key)
    if mode in {"include", "omit"}:
        return mode
    if service_option_values.get(text_key):
        return "include"
    return None


def _apply_prayers_named_value_for_prefixes(
    text, service_option_values, value_key, prefixes, trailing=""
):
    value = _sanitize_named_value(value_key, service_option_values)
    if not value:
        return text
    output = text or ""
    for prefix in prefixes:
        pattern = re.compile(rf"({re.escape(prefix)}) \[especially\s+_+\s*,?\]")
        updated = pattern.sub(
            rf"\1 [especially {value}{trailing}]",
            output,
            count=1,
        )
        if updated != output:
            return updated
    return output


def _apply_prayers_named_saints_insert_for_prefixes(
    text, service_option_values, prefixes
):
    value = _sanitize_named_value("prayers.saints.named_person", service_option_values)
    if not value:
        return text
    output = text or ""
    for prefix in prefixes:
        pattern = re.compile(rf"({re.escape(prefix)}) \[N\., and\]")
        updated = pattern.sub(rf"\1 [{value}, and]", output, count=1)
        if updated != output:
            return updated
    return output


def _sanitize_named_value(value_key, service_option_values):
    value = service_option_values.get(value_key)
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip().rstrip(",.;")
    return cleaned or None


def _alleluia_enabled(mode, season):
    if mode == "on":
        return True
    if mode == "off":
        return False
    if mode == "auto":
        return (season or "") in EASTER_ALLELUIA_SEASONS
    return None


def _apply_fraction_alleluia_mode(text, service_option_values, season):
    mode = service_option_values.get("fraction.alleluia_mode")
    enabled = _alleluia_enabled(mode, season)
    if enabled is None:
        return text

    if enabled:
        return (text or "").replace("[Alleluia.]", "Alleluia.")
    cleaned = re.sub(r"\s*\[Alleluia\.\]", "", text or "")
    cleaned = re.sub(r" {2,}", " ", cleaned)
    return cleaned


def _apply_dismissal_alleluia_mode(text, service_option_values, season):
    mode = service_option_values.get("dismissal.alleluia_mode")
    enabled = _alleluia_enabled(mode, season)
    if enabled is None:
        return text

    output = text or ""
    dismissal_sentences = [
        "Let us go forth in the Name of Christ.",
        "Go in peace to love and serve the Lord.",
        "Let us go forth into the world, rejoicing in the power of the Holy Spirit.",
        "Let us bless the Lord.",
    ]

    for sentence in dismissal_sentences:
        with_alleluia = f"{sentence} Alleluia, alleluia."
        if enabled:
            output = output.replace(sentence, with_alleluia)
        else:
            output = output.replace(with_alleluia, sentence)

    if enabled:
        output = output.replace(
            "**Thanks be to God.**", "**Thanks be to God. Alleluia, alleluia.**"
        )
    else:
        output = output.replace(
            "**Thanks be to God. Alleluia, alleluia.**", "**Thanks be to God.**"
        )
    return output
