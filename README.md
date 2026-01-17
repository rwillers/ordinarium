# Ordinarium: a liturgy planning workspace

> Work in progress as of December 2025.

Ordinarium is a liturgy planning workspace that incorporates the structure and rubrics of the Anglican Church in North America (ACNA) *Book of Common Prayer* (2019), enabling clergy and liturgists to assemble, order, and manage liturgical orders of service. It supports the selection of propers, readings, prayers, and ceremonial elements; their arrangement into a coherent liturgy; and export or sharing for use in planning, presentation, or printed materials. Though focused initially on Anglican eucharistic services, Ordinarium is designed to accommodate additional rites and traditions as the platform develops.

## Table of contents
- Overview
- Features
- Liturgical text conventions
- Data structure
- Tech stack
- Roadmap
- License

## Features
- Compose a full liturgical order by selecting propers, readings, and prayers from the ACNA 2019 BCP.
- Enforce rubrical sequencing while allowing flexible overrides for local practice.
- Export or share services for worship planning, presentation software, or printable leaflets.
- Planned: role-based access (clergy, musicians, readers), history/audit trail, and additional rite modules.

## Liturgical text conventions

All service texts are represented in Markdown.

- Service titles use H1 (e.g., "The Order for the Administration of the Lord’s Supper or Holy Communion, Commonly Called the Holy Eucharist").
- Service subtitles use H2 (e.g., "Renewed Ancient Text").
- Service sections use H3 (e.g., "The Acclamation").
- Rubrics use italic face.
- Celebrant text uses regular face.
- People text uses bold face (**Text**).
- References use H6.
- When there is optionality on the rendition of a piece of text (e.g., the Kyrie), an unordered list is used; for example (note double-space line breaks to preserve formatting):
    -   Lord, have mercy upon us.  
        **Christ, have mercy upon us.**  
        Lord, have mercy upon us.
    -   Lord, have mercy.  
        **Christ, have mercy.**  
        Lord, have mercy.
    -   Kyrie eleison.  
        **Christe eleison.**  
        Kyrie eleison.
- Preformatted text use double-space line breaks to preserve formatting (e.g., "We believe in one God,\[\_\]\[\_\]⮐").
- Preformatted paragraphs (e.g., the Creeds) use code (four spaces, resulting in <pre><code> blocks).
- Variables that are intended to be filled in with propers or other seasonal language are indicated using double curly quotation marks (e.g., "{{variable_name}}").

## Database structure

Note that the SQLite database uses JSON data storage fields with virtual columns. More information on the approach can be found [here](https://www.dbpro.app/blog/sqlite-json-virtual-columns-indexing). Properdata (holidays, fragments, subcycles) is embedded in `ordinarium/schema.sql` and applied to existing databases via `scripts/migrate_db.py`.

## Tech stack (planned)
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

## Roadmap

### MVP
- Implement initial export formats: PDF and DOCX.
- Code clean up.

### Post-MVP
- Add second BCP 2019 rite (Anglican Standard Text).
- Add additional liturgy templates (Morning Prayer, Compline, funerals, weddings; other prayer books/sacramentaries/missals).
- Add rich propers search with calendar/season awareness.
- Implement additional export formats and integrations: Planning Center, ProPresenter, etc.
- Add team accounts (shared services, element libraries).
- Add collaboration features for team accounts: comments, approvals, version history.
