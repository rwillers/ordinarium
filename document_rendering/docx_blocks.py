from .html_fragment import parse_fragment, serialize_children


def extract_inline_tokens(fragment):
    root = parse_fragment(fragment)
    return _trim_edge_breaks(_collect_inline_tokens(root))


def extract_blocks(fragment, treat_ul_as_variants=True):
    root = parse_fragment(fragment)
    blocks = []
    for child in root["children"]:
        if child["type"] == "text":
            if child["text"].strip():
                blocks.append(_text_block(child["text"]))
            continue

        tag = child["tag"]
        if tag in {"p", "h6"}:
            tokens = _trim_edge_breaks(_collect_inline_tokens(child))
            if _tokens_have_content(tokens):
                variant = "scripture" if tag == "h6" else "body"
                blocks.append(
                    {"kind": "paragraph", "variant": variant, "tokens": tokens}
                )
            continue
        if tag == "pre":
            text = _extract_pre_text(child)
            if text.strip():
                blocks.append({"kind": "pre", "text": text})
            continue
        if tag == "ul":
            blocks.extend(_extract_list_blocks(child, treat_ul_as_variants))
            continue
        blocks.extend(extract_blocks(serialize_children(child), treat_ul_as_variants))
    return blocks


def _text_block(text):
    return {
        "kind": "paragraph",
        "variant": "body",
        "tokens": _trim_edge_breaks(
            [{"kind": "text", "text": text, **_base_text_style()}]
        ),
    }


def _extract_list_blocks(node, treat_ul_as_variants):
    items = []
    for list_item in node["children"]:
        if list_item["type"] != "element" or list_item["tag"] != "li":
            continue
        tokens = _trim_edge_breaks(_collect_inline_tokens(list_item, parent_tag="li"))
        if _tokens_have_content(tokens):
            items.append(tokens)

    if not treat_ul_as_variants:
        return [{"kind": "bullet", "tokens": tokens} for tokens in items]

    blocks = []
    for index, tokens in enumerate(items):
        blocks.append({"kind": "paragraph", "variant": "body", "tokens": tokens})
        if index < len(items) - 1:
            blocks.append(
                {
                    "kind": "paragraph",
                    "variant": "body",
                    "tokens": [
                        {
                            "kind": "text",
                            "text": "Or",
                            "bold": False,
                            "italic": True,
                            "rubric": True,
                        }
                    ],
                }
            )
    return blocks


def _extract_pre_text(node):
    parts = []

    def visit(current):
        for child in current["children"]:
            if child["type"] == "text":
                parts.append(child["text"])
                continue
            if child["tag"] == "br":
                parts.append("\n")
                continue
            visit(child)

    visit(node)
    return "".join(parts).strip("\n")


def _collect_inline_tokens(node, style=None, parent_tag=""):
    style = style or _base_text_style()
    tokens = []
    for child in node["children"]:
        if child["type"] == "text":
            tokens.append({"kind": "text", "text": child["text"], **style})
            continue

        tag = child["tag"]
        if tag == "br":
            tokens.append({"kind": "break"})
            continue

        next_style = dict(style)
        if tag in {"strong", "b"}:
            next_style["bold"] = True
        if tag in {"em", "i"}:
            next_style["italic"] = True
            next_style["rubric"] = True
        if tag == "code":
            next_style["bold"] = True

        is_nested_paragraph = tag == "p" and parent_tag == "li"
        if is_nested_paragraph and tokens and tokens[-1]["kind"] != "break":
            tokens.append({"kind": "break"})
        child_tokens = _collect_inline_tokens(child, next_style, parent_tag=tag)
        tokens.extend(child_tokens)
        if is_nested_paragraph and child_tokens and tokens[-1]["kind"] != "break":
            tokens.append({"kind": "break"})
    return tokens


def _base_text_style():
    return {"bold": False, "italic": False, "rubric": False}


def _tokens_have_content(tokens):
    return any(token["kind"] == "text" and token["text"].strip() for token in tokens)


def _trim_edge_breaks(tokens):
    trimmed = list(tokens)
    while trimmed and trimmed[0]["kind"] == "break":
        trimmed.pop(0)
    while trimmed and trimmed[-1]["kind"] == "break":
        trimmed.pop()
    return trimmed
