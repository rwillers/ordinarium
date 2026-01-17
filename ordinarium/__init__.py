import html
import os
import re
from html.parser import HTMLParser

import markdown2
from jinja2 import pass_context
from markupsafe import Markup
from flask import Flask

from .db import close_db, init_db_command
from .routes import bp as main_bp


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "ordinarium.db"),
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
    )

    os.makedirs(app.instance_path, exist_ok=True)

    app.jinja_env.add_extension("jinja_markdown2.MarkdownExtension")
    extras = [
        "fenced-code-blocks",
        "code-friendly",
        # 'target-blank-links',
        "markdown-in-html",
        "footnotes",
    ]

    @pass_context
    def markdown_template(context, value):
        template = context.environment.from_string(value or "")
        rendered = template.render(context.get_all())
        html_text = markdown2.markdown(rendered, extras=extras)
        return Markup(html_text)

    def wrap_trailing_indent(value):
        if not value:
            return Markup("")

        trailing_span_re = re.compile(
            r'class=["\'][^"\']*\btrailing-indent\b[^"\']*["\']',
            re.IGNORECASE,
        )
        br_split_re = re.compile(r"(<br\s*/?>)", re.IGNORECASE)
        paragraph_re = re.compile(r"(<p\b[^>]*>)(.*?)(</p>)", re.DOTALL)

        def wrap_segment(segment):
            match = re.match(r"(\s*)(<em>.*?</em>)(.*)", segment, re.DOTALL)
            if not match:
                return segment
            leading, em_html, remainder = match.groups()
            if not remainder.strip():
                return segment
            if trailing_span_re.search(remainder):
                return segment
            return f"{leading}{em_html}<span class=\"trailing-indent\">{remainder}</span>"

        def wrap_paragraph(match):
            open_tag, inner, close_tag = match.groups()
            parts = br_split_re.split(inner)
            for index in range(0, len(parts), 2):
                parts[index] = wrap_segment(parts[index])
            return f"{open_tag}{''.join(parts)}{close_tag}"

        return Markup(paragraph_re.sub(wrap_paragraph, str(value)))

    app.jinja_env.filters["markdown"] = lambda value: Markup(
        markdown2.markdown(
            value or "",
            extras=extras,
        )
    )
    app.jinja_env.filters["markdown_template"] = markdown_template
    app.jinja_env.filters["trailing_indent"] = wrap_trailing_indent
    app.jinja_env.filters["clean"] = lambda value: re.sub(
        r"\s+", " ", value or ""
    ).strip()

    app.register_blueprint(main_bp)
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

    return app
