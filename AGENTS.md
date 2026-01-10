# Repository Guidelines

## Project Structure & Module Organization
- `app.py` is a small entrypoint that instantiates the Flask app for local runs.
- `ordinarium/` holds the application package: `__init__.py` (app factory, Jinja filters), `routes.py` (Flask blueprint), `db.py` and `schema.sql` (SQLite schema/init).
- `ordinarium/templates/` contains Jinja templates (page layout, plan, text views).
- `ordinarium/static/` contains CSS, images, and `manifest.json`.
- `instance/` stores the SQLite database (`ordinarium.db`) created locally by `init-db`.
- `Source Liturgies/` contains source material used for content reference.

## Build, Test, and Development Commands
- `python -m venv venv` and `source venv/bin/activate` to create/activate a virtual environment.
- `pip install -r requirements.txt` installs Flask and Markdown tooling.
- `flask --app ordinarium init-db` creates or resets `instance/ordinarium.db` from `ordinarium/schema.sql`.
- `flask --app ordinarium run` starts the dev server.
- `python app.py` is a quick dev run alternative with debug enabled.

## Coding Style & Naming Conventions
- Format Python with Black (4-space indentation). Run `black .` after Python changes.
- Prefer `snake_case` for functions, variables, and route helpers; keep route slugs lowercase with underscores.
- Template filenames are lowercase and descriptive (`plan.html`, `text.html`).
- Liturgical text conventions are documented in `README.md`; preserve Markdown formatting rules when editing content.

## Testing Guidelines
- No automated test suite is present yet.
- Manual verification: run the dev server and check `/`, `/services`, `/service/<id>`, and `/text/<rite_slug>` flows. If you touch DB logic, re-run `init-db` and verify a fresh database works.

## Commit & Pull Request Guidelines
- Existing commits use short, imperative, sentence-case summaries (e.g., “Add …”, “Enhance …”). Follow that pattern.
- PRs should include a short description, any relevant issue links, and screenshots for UI changes.
- If you change data shape or queries, call out required `init-db` steps in the PR description.

## Configuration & Data Tips
- Treat `instance/ordinarium.db` as local state; reset it with `flask --app ordinarium init-db` after schema updates.
- Keep secrets and environment-specific settings out of the repo; prefer `instance/` for local-only config.
