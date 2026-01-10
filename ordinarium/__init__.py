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

    app.jinja_env.filters["markdown"] = lambda value: Markup(
        markdown2.markdown(
            value or "",
            extras=extras,
        )
    )
    app.jinja_env.filters["markdown_template"] = markdown_template
    app.jinja_env.filters["clean"] = lambda value: re.sub(
        r"\s+", " ", value or ""
    ).strip()

    app.register_blueprint(main_bp)
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

    return app
