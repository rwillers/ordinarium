import html
import os
import re
from datetime import timedelta
from html.parser import HTMLParser
from functools import lru_cache

import markdown2
from flask import Flask
from flask_wtf import CSRFProtect
from jinja2 import pass_context
from markupsafe import Markup

from .db import close_db, init_db_command
from .auth_rate_limit import init_rate_limiter
from .mail_delivery import init_mail
from .auth_session import init_login
from .routes import bp as main_bp


def _is_dev_env():
    return (
        os.getenv("ORDINARIUM_DEBUG") == "1"
        or os.getenv("FLASK_DEBUG") == "1"
        or os.getenv("FLASK_ENV") == "development"
    )


def _config_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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
        PASSWORD_RESET_DELIVERY_KEY=os.environ.get("PASSWORD_RESET_DELIVERY_KEY"),
        TURNSTILE_ENABLED=_config_bool(
            os.environ.get("TURNSTILE_ENABLED"), not _is_dev_env()
        ),
        TURNSTILE_SITE_KEY=os.environ.get("TURNSTILE_SITE_KEY"),
        TURNSTILE_SECRET_KEY=os.environ.get("TURNSTILE_SECRET_KEY"),
        TURNSTILE_EXPECTED_HOSTNAME=os.environ.get("TURNSTILE_EXPECTED_HOSTNAME"),
        SMTP_HOST=os.environ.get("SMTP_HOST"),
        SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USERNAME=os.environ.get("SMTP_USERNAME"),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD"),
        SMTP_USE_TLS=os.environ.get("SMTP_USE_TLS", "true"),
        SMTP_USE_SSL=os.environ.get("SMTP_USE_SSL", "false"),
        SMTP_SENDER=os.environ.get("SMTP_SENDER"),
        MAIL_SERVER=os.environ.get("SMTP_HOST"),
        MAIL_PORT=int(os.environ.get("SMTP_PORT", "587")),
        MAIL_USERNAME=os.environ.get("SMTP_USERNAME"),
        MAIL_PASSWORD=os.environ.get("SMTP_PASSWORD"),
        MAIL_USE_TLS=_config_bool(os.environ.get("SMTP_USE_TLS", "true"), True),
        MAIL_USE_SSL=_config_bool(os.environ.get("SMTP_USE_SSL", "false"), False),
        MAIL_DEFAULT_SENDER=os.environ.get("SMTP_SENDER"),
        RATELIMIT_ENABLED=_config_bool(
            os.environ.get("RATELIMIT_ENABLED", "true"), True
        ),
        RATELIMIT_STORAGE_URI=os.environ.get("RATELIMIT_STORAGE_URI"),
        RATELIMIT_LOGIN=os.environ.get("RATELIMIT_LOGIN", "10/minute"),
        RATELIMIT_SIGNUP=os.environ.get("RATELIMIT_SIGNUP", "10/minute"),
        RATELIMIT_PASSWORD_RESET=os.environ.get("RATELIMIT_PASSWORD_RESET", "5/minute"),
        PCO_API_BASE=os.environ.get(
            "PCO_API_BASE", "https://api.planningcenteronline.com"
        ),
        PCO_OAUTH_AUTHORIZE_URL=os.environ.get(
            "PCO_OAUTH_AUTHORIZE_URL",
            "https://api.planningcenteronline.com/oauth/authorize",
        ),
        PCO_OAUTH_TOKEN_URL=os.environ.get(
            "PCO_OAUTH_TOKEN_URL",
            "https://api.planningcenteronline.com/oauth/token",
        ),
        PCO_CLIENT_ID=os.environ.get("PCO_CLIENT_ID"),
        PCO_CLIENT_SECRET=os.environ.get("PCO_CLIENT_SECRET"),
        PCO_TOKEN_ENCRYPTION_KEYS=os.environ.get("PCO_TOKEN_ENCRYPTION_KEYS"),
        PCO_TOKEN_ENCRYPTION_KEY=os.environ.get("PCO_TOKEN_ENCRYPTION_KEY"),
        PCO_TOKEN_ENCRYPTION_PRIMARY_VERSION=os.environ.get(
            "PCO_TOKEN_ENCRYPTION_PRIMARY_VERSION", "v1"
        ),
        PCO_OAUTH_REDIRECT_URI=os.environ.get("PCO_OAUTH_REDIRECT_URI"),
        PCO_OAUTH_SCOPES=os.environ.get("PCO_OAUTH_SCOPES", "services"),
        DOCUMENT_SERVICE_URL=os.environ.get("DOCUMENT_SERVICE_URL"),
        DOCUMENT_SERVICE_TIMEOUT_SECONDS=float(
            os.environ.get("DOCUMENT_SERVICE_TIMEOUT_SECONDS", "120")
        ),
        DOCUMENT_SERVICE_MAX_REQUEST_BYTES=int(
            os.environ.get("DOCUMENT_SERVICE_MAX_REQUEST_BYTES", str(5 * 1024 * 1024))
        ),
        DOCUMENT_SERVICE_MAX_BYTES=int(
            os.environ.get("DOCUMENT_SERVICE_MAX_BYTES", str(25 * 1024 * 1024))
        ),
        QUEUE_SERVICE_URL=os.environ.get("QUEUE_SERVICE_URL"),
        QUEUE_SERVICE_TIMEOUT_SECONDS=float(
            os.environ.get("QUEUE_SERVICE_TIMEOUT_SECONDS", "10")
        ),
        DATABASE_GATEWAY_BACKEND=os.environ.get("DATABASE_GATEWAY_BACKEND", "sqlite"),
        D1_SERVICE_URL=os.environ.get("D1_SERVICE_URL"),
        D1_SERVICE_TIMEOUT_SECONDS=float(
            os.environ.get("D1_SERVICE_TIMEOUT_SECONDS", "30")
        ),
        D1_SERVICE_MAX_BYTES=int(
            os.environ.get("D1_SERVICE_MAX_BYTES", str(5 * 1024 * 1024))
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE=os.environ.get("SESSION_COOKIE_SAMESITE", "Lax"),
        SESSION_COOKIE_SECURE=_config_bool(
            os.environ.get("SESSION_COOKIE_SECURE", "false"), False
        ),
        PERMANENT_SESSION_LIFETIME=timedelta(
            days=int(os.environ.get("SESSION_LIFETIME_DAYS", "30"))
        ),
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

    @lru_cache(maxsize=512)
    def _render_markdown_cached(value, safe_mode):
        html_text = markdown2.markdown(
            value or "",
            extras=extras,
            safe_mode=safe_mode,
        )
        return _decorate_lesson_reference_links(html_text)

    def render_markdown(value, safe_mode=None):
        return _render_markdown_cached(value or "", safe_mode)

    def _decorate_lesson_reference_links(value):
        if not value:
            return value
        return re.sub(
            r'<a href="(https://biblia\.com/books/[^"]+)">',
            (
                r'<a class="lesson-reference-link" href="\1" '
                r'target="_blank" rel="noopener noreferrer">'
            ),
            value,
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
            return f'{leading}{em_html}<span class="trailing-indent">{remainder}</span>'

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
    CSRFProtect(app)
    init_login(app)
    init_mail(app)
    init_rate_limiter(app)

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
