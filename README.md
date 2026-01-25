# Ordinarium: a liturgy planning workspace

Ordinarium is a liturgy planning workspace that incorporates the structure and rubrics of the Anglican Church in North America (ACNA) *Book of Common Prayer* (2019), enabling clergy and liturgists to assemble, order, and manage liturgical orders of service. It supports the selection of propers, readings, prayers, and ceremonial elements; their arrangement into a coherent liturgy; and export or sharing for use in planning, presentation, or printed materials. Though focused initially on Anglican eucharistic services, Ordinarium is designed to accommodate additional rites and traditions as the platform develops.

## Table of contents
- Overview
- Features
- Liturgical text conventions
- Database structure
- Tech stack
- Development
- Roadmap

## Features
- Compose a full liturgical order by selecting propers, readings, and prayers from the ACNA 2019 BCP.
- Enforce rubrical sequencing while allowing flexible overrides for local practice.
- Export or share services for worship planning and, in the future, presentation software or printable leaflets.
- Planned: role-based access (e.g., clergy, musicians, readers), history/audit trail, and support for additional rites.

## Liturgical text conventions

All service texts are represented in Markdown.

- Service titles use H1 (e.g., "The Order for the Administration of the Lord’s Supper or Holy Communion, Commonly Called the Holy Eucharist").
- Service subtitles use H2 (e.g., "Renewed Ancient Text").
- Service sections use H3 (e.g., "The Acclamation").
- Rubrics use italic face.
- Celebrant text uses regular face.
- People text uses bold face (**Text**).
- Scripture references use H6.
- When there is optionality on the rendition of a piece of text (e.g., the Kyrie), an unordered list is used, including use of double-space line breaks to preserve formatting.
- Preformatted text uses double-space line breaks to preserve formatting (e.g., "We believe in one God,\[\_\]\[\_\]⮐").
- Preformatted paragraphs (e.g., the Creeds) use code formatting (four spaces, resulting in \<pre\>\<code\> blocks).
- Variables that are intended to be filled in with propers or other seasonal language are indicated using double curly quotation marks (e.g., "{{variable_name}}").
- App UI titles and headers use sentence case (e.g., "Propers search").

## Database structure

Note that the SQLite database materializes former JSON virtual columns into real columns, while still storing JSON payloads in specific fields (for example `services.text_order`, `services.text_disabled`, `services.lesson_overrides`, and `texts.subcycles`). Properdata (holidays, fragments, subcycles) is embedded in `ordinarium/schema.sql` and applied to existing databases via `scripts/migrate_db.py`.
When updating JSON text fields via SQL migrations, prefer building multiline strings with `char(10)` concatenation instead of embedding `\n` escapes; SQLite may preserve literal `\n` sequences, which then render as backslashes in output.

## Tech stack
- Python 3.11+
- Flask (Jinja templates, blueprints)
- SQLite
- HTML/CSS/JS front end
- Gunicorn for production serving

## Development (local)
1) Create and activate a virtual environment.
2) Install dependencies: `pip install -r requirements.txt`.
3) Initialize the database: `flask --app ordinarium init-db`.
4) If upgrading an existing database, run `python scripts/migrate_db.py`.
5) Run the app: `flask --app ordinarium run`.
6) Alternate run (debug enabled): `ORDINARIUM_DEBUG=1 python app.py`.

## Roadmap
- Implement export formats: PDF (already supported through custom print stylesheet) and DOCX.
- Add additional liturgy templates (Morning Prayer, Compline, funerals, weddings; other prayer books/sacramentaries/missals).
- Implement additional export formats and integrations: Planning Center, ProPresenter, etc.
- Add team accounts (shared services and element libraries).
- Add collaboration features for team accounts: comments, approvals, version history.
