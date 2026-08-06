import re

from flask import current_app, render_template

from document_rendering import render_docx_bytes, render_pdf_bytes
from document_rendering.html_fragment import parse_fragment as _parse_fragment

from .text_rendering import build_rendered_ordinaries

PRINT_RUBRIC_COLOR = "C62F7C"

EXPORT_TEXT_CSS = """
@page {
    margin: 1in;
}

html, body {
    margin: 0;
    padding: 0;
}

body {
    background: #fff;
    color: #000;
    font-family: Georgia, serif;
    font-size: 11pt;
}

#text {
    padding-top: 0;
}

#text h1 {
    font-size: 1.36em;
    font-weight: 200;
    text-align: center;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    line-height: 1.67em;
    margin: 0.67em 0;
}

#text h1 small {
    display: inline-block;
    font-size: 0.8em;
    letter-spacing: 0.1em;
    color: #c62f7c;
}

#text h1 small em {
    font-size: 0.67em;
    text-transform: none;
}

#text h2 {
    font-size: 1.1em;
    font-weight: 400;
    font-style: italic;
    text-align: center;
    color: #c62f7c;
    margin: 0.83em 0;
}

#text h3 {
    font-size: 0.91em;
    font-weight: 400;
    letter-spacing: 0.1em;
    text-align: center;
    text-transform: uppercase;
    color: #c62f7c;
    margin: 1em 0;
    break-after: avoid-page;
}

#text h6 {
    font-size: 0.82em;
    font-weight: 400;
    text-align: right;
    text-transform: uppercase;
    color: #c62f7c;
    margin: -1.11em 0 1.11em 0;
}

#text strong {
    font-weight: 600;
}

#text p em,
#text li em,
#text pre em,
#text code em {
    font-style: italic;
    color: #c62f7c;
}

#text small {
    font-size: 0.81em;
}

#text p {
    margin: 0.91em 0;
    break-inside: avoid;
}

#text pre {
    margin: 0 auto;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    break-inside: avoid;
}

#text code {
    color: #000;
    font-size: 1em;
    font-family: Georgia, serif;
    font-weight: 600;
}

#text .text-element:not(.text-element-custom) ul {
    margin: 0;
    padding: 0;
    list-style: none;
}

#text .variant-list {
    margin: 0.2em 0 0.9em;
}

#text .variant-option p {
    margin: 0.5em 0;
}

#text .variant-or {
    margin: 0.25em 0;
    text-align: center;
}

#text .variant-or em {
    color: #c62f7c;
    font-style: italic;
}

#text .text-element.text-element-custom ul {
    margin: 0.5em 0 0.9em 1.4em;
    padding: 0;
    list-style: disc;
}

#text .text-element.text-element-custom ul li {
    display: list-item;
    white-space: normal;
}

#text .text-element.text-element-custom ul li + li {
    margin-top: 0.25em;
}

#text p > em:first-child:not(:last-child) {
    display: inline-block;
    margin-right: 0.5em;
    min-width: 4.5em;
    font-size: 0.91em;
    text-align: right;
}

#text p > .trailing-indent {
    display: inline-block;
    width: calc(100% - 5em);
    vertical-align: top;
}

#text .text-footer {
    font-size: 0.8em;
    text-align: center;
    margin-top: 2em;
    color: #c62f7c;
}
"""


def build_text_export_context(service_id, saved_service, saved_data, user_id=None):
    payload = build_rendered_ordinaries(
        service_id,
        saved_service,
        saved_data,
        user_id=user_id,
        include_metadata=True,
        link_lesson_references=False,
    )
    if not payload:
        return None

    markdown_filter = current_app.jinja_env.filters.get("markdown")
    markdown_user_filter = current_app.jinja_env.filters.get("markdown_user")
    trailing_indent_filter = current_app.jinja_env.filters.get("trailing_indent")

    if not markdown_filter or not markdown_user_filter or not trailing_indent_filter:
        raise RuntimeError("Required markdown filters are not configured.")

    ordinaries = []
    previous_title = None
    for ordinary in payload["ordinaries"]:
        render_markdown = (
            markdown_user_filter
            if ordinary.get("type") == "custom" or ordinary.get("house_use_applied")
            else markdown_filter
        )
        title_markdown = ordinary.get("title") or ""
        title_html = str(render_markdown(title_markdown))
        title_inline_html = _strip_wrapping_paragraph(title_html)

        body_markdown = ordinary.get("text") or ""
        body_html = str(render_markdown(body_markdown))
        body_html = str(trailing_indent_filter(body_html))
        if ordinary.get("type") != "custom" and not ordinary.get("house_use_content"):
            body_html = _rewrite_variant_lists(body_html)

        show_title = bool(title_markdown) and title_markdown != previous_title
        previous_title = title_markdown

        ordinaries.append(
            {
                "type": ordinary.get("type"),
                "house_use_applied": bool(ordinary.get("house_use_applied")),
                "house_use_embedded": bool(ordinary.get("house_use_embedded")),
                "house_use_content": bool(ordinary.get("house_use_content")),
                "title_markdown": title_markdown,
                "title_inline_html": title_inline_html,
                "body_html": body_html,
                "show_title": show_title,
            }
        )

    payload["service_id"] = service_id
    payload["ordinaries"] = ordinaries
    return payload


def render_text_export_html(context):
    return render_template("export_text.html", export_css=EXPORT_TEXT_CSS, **context)


def build_docx_render_context(context):
    scalar_keys = (
        "title",
        "rite",
        "service_title",
        "service_date_display",
        "generated_at_display",
    )
    document_context = {key: context.get(key) for key in scalar_keys}
    document_context["ordinaries"] = [
        {
            "type": ordinary.get("type"),
            "house_use_applied": bool(ordinary.get("house_use_applied")),
            "house_use_embedded": bool(ordinary.get("house_use_embedded")),
            "house_use_content": bool(ordinary.get("house_use_content")),
            "title_inline_html": ordinary.get("title_inline_html", ""),
            "body_html": ordinary.get("body_html", ""),
            "show_title": bool(ordinary.get("show_title")),
        }
        for ordinary in context.get("ordinaries", [])
    ]
    return document_context


def build_export_filename(context, extension):
    base_parts = []
    service_date = context.get("service_date")
    if service_date:
        base_parts.append(service_date)
    service_title = context.get("service_title") or context.get("title")
    if service_title:
        base_parts.append(service_title)
    base = " ".join(base_parts).strip() or f"service-{context.get('service_id', '')}"
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    if not slug:
        slug = f"service-{context.get('service_id', '')}"
    return f"{slug}.{extension}"


def _strip_wrapping_paragraph(value):
    if not value:
        return ""
    match = re.fullmatch(r"\s*<p\b[^>]*>(.*)</p>\s*", value, flags=re.DOTALL)
    if not match:
        return value.strip()
    inner = match.group(1).strip()
    if "<p" in inner.lower():
        return value.strip()
    return inner


def _rewrite_variant_lists(fragment):
    root = _parse_fragment(fragment)
    return "".join(
        _serialize_node_with_variant_lists(child) for child in root["children"]
    )


def _serialize_node_with_variant_lists(node):
    if node["type"] == "text":
        return node["text"]

    tag = node["tag"]
    if tag == "br":
        return "<br>"
    if tag == "ul":
        options = [
            child
            for child in node["children"]
            if child["type"] == "element" and child["tag"] == "li"
        ]
        if not options:
            return ""
        parts = ['<div class="variant-list">']
        for index, option in enumerate(options):
            parts.append('<div class="variant-option">')
            parts.extend(
                _serialize_node_with_variant_lists(child)
                for child in option["children"]
            )
            parts.append("</div>")
            if index < len(options) - 1:
                parts.append('<p class="variant-or"><em>Or</em></p>')
        parts.append("</div>")
        return "".join(parts)

    attrs = "".join(f' {key}="{value}"' for key, value in node["attrs"].items())
    inner = "".join(
        _serialize_node_with_variant_lists(child) for child in node["children"]
    )
    return f"<{tag}{attrs}>{inner}</{tag}>"
