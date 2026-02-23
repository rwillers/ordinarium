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
        elif title == "the confession and absolution of sin":
            text = _apply_confession_invitation_form(text, service_option_values)
        elif title == "the fraction":
            text = _apply_fraction_alleluia_mode(text, service_option_values, season)
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
