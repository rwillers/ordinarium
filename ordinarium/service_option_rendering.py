import re


EASTER_ALLELUIA_SEASONS = {"Easter", "Ascension", "Pentecost"}


def apply_service_option_overrides(ordinaries, service_option_values, season=None):
    if not isinstance(ordinaries, list) or not ordinaries:
        return ordinaries
    if not isinstance(service_option_values, dict):
        return ordinaries

    updated = []
    for item in ordinaries:
        output = dict(item)
        if output.get("type") == "custom":
            updated.append(output)
            continue
        title = _normalize_title(output.get("title"))
        detailed_title = _normalize_title(output.get("detailed_title"))
        text = output.get("text") or ""
        penitential_mode = service_option_values.get("penitential_song.mode")
        if title == "the kyrie" and penitential_mode == "trisagion":
            continue
        if title == "the trisagion" and penitential_mode == "kyrie":
            continue
        if title == "the summary of the law":
            text = _apply_law_form(text, service_option_values)
        elif title == "the kyrie":
            text = _apply_kyrie_form(text, service_option_values)
        if title == "the lord's prayer":
            text = _apply_lords_prayer_form(text, service_option_values)
        elif title == "the nicene creed":
            text = _apply_creed_filioque_clause(text, service_option_values)
        elif title == "the comfortable words":
            text = _apply_comfortable_words_sentences(text, service_option_values)
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
        elif title == "the lessons" and detailed_title == "the lessons (psalter)":
            text = _apply_psalm_gloria_patri(text, service_option_values)
        output["text"] = text
        updated.append(output)
    return updated


def _normalize_title(value):
    cleaned = (value or "").replace("’", "'")
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def _apply_law_form(text, service_option_values):
    form = service_option_values.get("law.form")
    if form == "summary":
        return (text or "").replace(
            "Then follows the Summary of the Law, or The Decalogue (page 100).",
            "Then follows the Summary of the Law.",
        )
    if form == "decalogue":
        return "*Then follows the Decalogue (page 100).*"
    return text


def _apply_kyrie_form(text, service_option_values):
    mode = service_option_values.get("penitential_song.mode")
    if mode and mode != "kyrie":
        return text
    form = service_option_values.get("kyrie.form")
    if not form and mode != "kyrie":
        return text
    choice_index = {
        "traditional": 0,
        "contemporary": 1,
        "greek": 2,
    }.get(form or "traditional")

    base = (text or "").split("\n\n*or this*", 1)[0]
    bullet_starts = [match.start() for match in re.finditer(r"(?m)^-\s+", base)]
    if not bullet_starts:
        return base
    bullet_blocks = []
    for index, start in enumerate(bullet_starts):
        end = bullet_starts[index + 1] if index + 1 < len(bullet_starts) else len(base)
        bullet_blocks.append(base[start:end].strip())
    if choice_index is None or choice_index >= len(bullet_blocks):
        return base

    heading = base[: bullet_starts[0]].rstrip()
    selected = bullet_blocks[choice_index].strip()
    return f"{heading}\n\n{selected}"


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


def _apply_comfortable_words_sentences(text, service_option_values):
    selected = _resolve_comfortable_words_selection(service_option_values)
    if not selected:
        return text

    pattern = re.compile(
        r"(?s)"
        r"(.*?Hear the Word of God to all who truly turn to him\.\n\n)"
        r"(Come to me, all who labor and are heavy laden, and I will give you rest\.\s*\n###### Matthew 11:28)\n\n"
        r"(God so loved the world, that he gave his only-begotten Son, that whoever believes in him should not perish but have eternal life\.\s*\n###### John 3:16T)\n\n"
        r"(The saying is trustworthy and deserving of full acceptance, that Christ Jesus came into the world to save sinners\.\s*\n###### 1 Timothy 1:15)\n\n"
        r"(If anyone sins, we have an advocate with the Father, Jesus Christ the righteous\. He is the propitiation for our sins, and not for ours only, but also for the sins of the whole world\.\s*\n###### 1 John 2:1-2T)"
        r"(.*)"
    )
    match = pattern.fullmatch(text or "")
    if not match:
        return text

    sentence_map = {
        "matthew_11_28": match.group(2).strip(),
        "john_3_16": match.group(3).strip(),
        "first_timothy_1_15": match.group(4).strip(),
        "first_john_2_1_2": match.group(5).strip(),
    }
    ordered_selection = [
        sentence_map[key]
        for key in (
            "matthew_11_28",
            "john_3_16",
            "first_timothy_1_15",
            "first_john_2_1_2",
        )
        if key in selected
    ]
    if not ordered_selection:
        return text

    selected_block = "\n\n".join(ordered_selection)
    return f"{match.group(1)}{selected_block}{match.group(6)}"


def _apply_prayers_bracket_clauses(text, service_option_values):
    output = text or ""
    output = _apply_ast_prayers_profile_substitutions(output, service_option_values)
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


def _apply_ast_prayers_profile_substitutions(text, service_option_values):
    output = text or ""
    profile = _resolve_ast_profile(service_option_values)
    default_civil_title, default_clergy_title = _ast_profile_defaults(profile)

    civil_name = (
        _sanitize_named_value("prayers.ast.civil_leader.name", service_option_values)
        or "N"
    )
    civil_title = _resolve_ast_civil_title(service_option_values) or default_civil_title
    output = re.sub(
        r"especially N,\s+our President/Sovereign/Prime Minister,",
        f"especially {civil_name}, our {civil_title},",
        output,
        count=1,
    )

    clergy_name = (
        _sanitize_named_value("prayers.ast.clergy.name", service_option_values) or "N"
    )
    clergy_title = (
        _resolve_ast_clergy_title(service_option_values) or default_clergy_title
    )
    output = re.sub(
        r"especially to your servant\(s\) N,\s+our Archbishop/Bishop/Priest/Deacon, etc\.,",
        f"especially to your servant(s) {clergy_name}, our {clergy_title}, etc.,",
        output,
        count=1,
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

    output = f"{match.group(1)}{match.group(selected_group)}{match.group(6)}"
    # When a non-default dismissal form is explicitly selected, the trailing
    # seasonal instruction block no longer applies to a choice among all forms.
    if form and form != "go_forth_name_of_christ":
        return _strip_dismissal_alleluia_rubric(output)
    return output


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
    output = _apply_bracket_clause_with_text_option(
        output,
        "communion.invitation.appended_clause",
        "communion.invitation.appended_text",
        "The gifts of God for the people of God.",
        service_option_values,
    )
    output = _apply_bracket_clause_with_text_option(
        output,
        "communion.distribution.body_clause",
        "communion.distribution.body_text",
        "The Body of our Lord Jesus Christ,",
        service_option_values,
    )
    output = _apply_bracket_clause_with_text_option(
        output,
        "communion.distribution.blood_clause",
        "communion.distribution.blood_text",
        "The Blood of our Lord Jesus Christ,",
        service_option_values,
    )
    return output


def _apply_bracket_clause_with_text_option(
    text, mode_key, text_key, prefix, service_option_values
):
    mode = _resolve_include_omit_mode(service_option_values, mode_key, text_key)
    replacement_text = _sanitize_clause_text(text_key, service_option_values)
    return _apply_bracket_clause_mode_with_text(text, mode, prefix, replacement_text)


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


def _apply_bracket_clause_mode_with_text(text, mode, prefix, replacement_text):
    if mode not in {"include", "omit"}:
        return text
    pattern = re.compile(rf"({re.escape(prefix)}) \[(.+?)\]")
    match = pattern.search(text or "")
    if not match:
        return text
    if mode == "omit":
        return pattern.sub(r"\1", text, count=1)
    if replacement_text:
        return pattern.sub(
            lambda match: f"{match.group(1)} {replacement_text}", text, count=1
        )
    return pattern.sub(r"\1 \2", text, count=1)


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


def _sanitize_clause_text(value_key, service_option_values):
    value = service_option_values.get(value_key)
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned or None


def _resolve_comfortable_words_selection(service_option_values):
    value = service_option_values.get("comfortable_words.sentences")
    if not isinstance(value, list):
        return set()
    return {
        item
        for item in value
        if item
        in {
            "matthew_11_28",
            "john_3_16",
            "first_timothy_1_15",
            "first_john_2_1_2",
        }
    }


def _resolve_ast_civil_title(service_option_values):
    value = service_option_values.get("prayers.ast.civil_leader.title")
    title_map = {
        "president": "President",
        "sovereign": "Sovereign",
        "prime_minister": "Prime Minister",
    }
    return title_map.get(value)


def _resolve_ast_clergy_title(service_option_values):
    value = service_option_values.get("prayers.ast.clergy.title")
    title_map = {
        "archbishop": "Archbishop",
        "bishop": "Bishop",
        "priest": "Priest",
        "deacon": "Deacon",
    }
    return title_map.get(value)


def _resolve_ast_profile(service_option_values):
    value = service_option_values.get("prayers.ast.profile")
    if value in {"american", "commonwealth"}:
        return value
    return "american"


def _ast_profile_defaults(profile):
    if profile == "commonwealth":
        return "Sovereign", "Archbishop"
    return "President", "Bishop"


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
        output = (text or "").replace("[Alleluia.]", "Alleluia.")
    else:
        output = re.sub(r"\s*\[Alleluia\.\]", "", text or "")
        output = re.sub(r" {2,}", " ", output)
    return _strip_fraction_alleluia_rubric(output)


def _strip_fraction_alleluia_rubric(text):
    return re.sub(
        r"\n\n\*In Lent, Alleluia is omitted, and may be omitted at other times except during Easter Season\.\*",
        "",
        text or "",
        count=1,
    )


def _strip_dismissal_alleluia_rubric(text):
    return re.sub(
        r"(?s)\n\n\*From the Easter Vigil through the Day of Pentecost, “Alleluia, alleluia” is added to any of the dismissals\. It may be added at other times, except during Lent and on other penitential occasions\.\*\n\n\*The People respond\*\n\n\*\*Thanks be to God\.(?: Alleluia, alleluia\.)?\*\*",
        "",
        text or "",
        count=1,
    )


def _apply_psalm_gloria_patri(text, service_option_values):
    mode = service_option_values.get("psalm.gloria_patri")
    if mode not in {"include", "omit"}:
        return text

    output = text or ""
    rubric = "\n\n*At the end of the psalm the Gloria Patri (Glory be...) may be sung or said*"
    gloria_block = (
        "\n\n    Glory be to the Father, and to the Son, and to the Holy Spirit; *\n"
        "        as it was in the beginning, is now, and ever shall be,\n"
        "        world without end. Amen."
    )
    if mode == "include":
        return output.replace(rubric, "", 1)
    output = output.replace(rubric + gloria_block, "", 1)
    output = output.replace(rubric, "", 1)
    return output


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
    return _strip_dismissal_alleluia_rubric(output)
