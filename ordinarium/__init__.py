import html
import os
import re
import secrets
from html.parser import HTMLParser

import markdown2
from jinja2 import pass_context
from markupsafe import Markup
from flask import Flask, session

from .db import close_db, init_db_command
from .routes import bp as main_bp


def _is_dev_env():
    return (
        os.getenv("ORDINARIUM_DEBUG") == "1"
        or os.getenv("FLASK_DEBUG") == "1"
        or os.getenv("FLASK_ENV") == "development"
    )


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key and _is_dev_env():
        secret_key = "dev"
    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "ordinarium.db"),
        SECRET_KEY=secret_key,
        PASSWORD_RESET_EXPIRY_MINUTES=int(
            os.environ.get("PASSWORD_RESET_EXPIRY_MINUTES", "60")
        ),
        TURNSTILE_SITE_KEY=os.environ.get("TURNSTILE_SITE_KEY"),
        TURNSTILE_SECRET_KEY=os.environ.get("TURNSTILE_SECRET_KEY"),
        SMTP_HOST=os.environ.get("SMTP_HOST"),
        SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USERNAME=os.environ.get("SMTP_USERNAME"),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD"),
        SMTP_USE_TLS=os.environ.get("SMTP_USE_TLS", "true"),
        SMTP_USE_SSL=os.environ.get("SMTP_USE_SSL", "false"),
        SMTP_SENDER=os.environ.get("SMTP_SENDER"),
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

    def render_markdown(value, safe_mode=None):
        return markdown2.markdown(
            value or "",
            extras=extras,
            safe_mode=safe_mode,
        )

    @pass_context
    def markdown_template(context, value):
        template = context.environment.from_string(value or "")
        rendered = template.render(context.get_all())
        html_text = render_markdown(rendered)
        return Markup(html_text)

    def markdown_user(value):
        return Markup(render_markdown(value, safe_mode="escape"))

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

    app.jinja_env.filters["markdown"] = lambda value: Markup(render_markdown(value))
    app.jinja_env.filters["markdown_template"] = markdown_template
    app.jinja_env.filters["markdown_user"] = markdown_user
    app.jinja_env.filters["trailing_indent"] = wrap_trailing_indent
    app.jinja_env.filters["clean"] = lambda value: re.sub(
        r"\s+", " ", value or ""
    ).strip()
    app.jinja_env.globals["csrf_token"] = lambda: session.setdefault(
        "_csrf_token", secrets.token_urlsafe(32)
    )

    app.register_blueprint(main_bp)
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    @app.before_request
    def _require_secret_key():
        if app.testing or app.debug or _is_dev_env():
            return None
        secret = app.config.get("SECRET_KEY")
        if not secret or secret == "dev":
            raise RuntimeError("SECRET_KEY must be set in production.")
        return None

    return app
