from datetime import date, timedelta

from flask import current_app, g, jsonify, render_template, request, send_from_directory

from .db import get_db
from .error_pages import render_error
from .feature_flags import FEATURE_PCO_SYNC, user_has_feature
from .liturgical_calendar import (
    resolve_observance,
    resolve_observance_options,
    resolve_season,
)
from .pco_auth import get_valid_pco_connection
from .pco_sync_status import resolve_pco_sync_state
from .service_planning import (
    _build_lesson_readings,
    _format_lesson_reference,
    _resolve_collect_text,
    _resolve_lesson_references,
    _resolve_seasonal_text,
)
from .service_formatting import format_services


def register_page_routes(bp):
    @bp.route("/favicon.ico")
    def favicon():
        if current_app.static_folder is None:
            return "", 404
        return send_from_directory(
            current_app.static_folder,
            "images/favicon.ico",
            mimetype="image/vnd.microsoft.icon",
        )

    @bp.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @bp.route("/")
    def index():
        upcoming_services = []
        pco_enabled = False
        if g.user:
            db = get_db()
            today = date.today().isoformat()
            rows = db.execute(
                "select id, title, season, service_date, rite, observance_handle, updated_at from services where user_id=? and service_date is not null and service_date >= ? order by service_date asc limit 3",
                (g.user["id"], today),
            ).fetchall()
            upcoming_services = format_services(rows)
            pco_enabled = user_has_feature(g.user, FEATURE_PCO_SYNC)
            if pco_enabled:
                try:
                    pco_connected = bool(get_valid_pco_connection(g.user["id"], db))
                except Exception:
                    pco_connected = False
                pco_links = {}
                if pco_connected and upcoming_services:
                    service_ids = [service["id"] for service in upcoming_services]
                    placeholders = ",".join(["?"] * len(service_ids))
                    link_rows = db.execute(
                        f"""
                        select
                          service_id,
                          last_synced_at,
                          last_sync_status
                        from service_pco_links
                        where service_id in ({placeholders})
                        """,
                        service_ids,
                    ).fetchall()
                    pco_links = {row["service_id"]: dict(row) for row in link_rows}
                for service in upcoming_services:
                    if not pco_connected:
                        service["pco_status"] = {
                            "state": "disconnected",
                            "icon_state": "unlinked",
                            "label": "Not connected",
                        }
                        continue
                    pco_link = pco_links.get(service["id"])
                    if not pco_link:
                        service["pco_status"] = {
                            "state": "unlinked",
                            "icon_state": "unlinked",
                            "label": "Not linked",
                        }
                        continue
                    sync_state = resolve_pco_sync_state(
                        service.get("updated_at"),
                        pco_link.get("last_synced_at"),
                        pco_link.get("last_sync_status"),
                    )
                    status_label = "Synced"
                    status_icon = "synced"
                    if sync_state == "failed":
                        status_label = "Last sync failed"
                        status_icon = "unsynced"
                    elif sync_state == "unsynced":
                        status_label = "Unsynced changes"
                        status_icon = "unsynced"
                    service["pco_status"] = {
                        "state": sync_state,
                        "icon_state": status_icon,
                        "label": status_label,
                    }
        return render_template(
            "home.html", upcoming_services=upcoming_services, pco_enabled=pco_enabled
        )

    @bp.route("/about")
    def about():
        return render_template("about.html")

    @bp.route("/propers-search")
    def propers_search():
        today = date.today()
        days_until_sunday = (6 - today.weekday()) % 7
        default_date = (today + timedelta(days=days_until_sunday)).isoformat()
        return render_template("propers_search.html", today=default_date)

    @bp.route("/propers-search/results")
    def propers_search_results():
        raw_date = request.args.get("date", "")
        if not raw_date:
            return jsonify({"date": None, "season": None, "observances": []})
        try:
            service_date = date.fromisoformat(raw_date)
        except ValueError:
            return jsonify({"date": raw_date, "season": None, "observances": []})
        season = resolve_season(service_date)
        options = resolve_observance_options(service_date)
        if not options:
            return jsonify({"date": raw_date, "season": season, "observances": []})
        db = get_db()
        markdown = current_app.jinja_env.filters["markdown"]
        acclamation_text = _resolve_seasonal_text(db, "acclamation", season)
        proper_preface_text = _resolve_seasonal_text(db, "proper_preface", season)
        observances = []
        for observance in options:
            propers_list = list(observance.propers)
            readings = _build_lesson_readings(propers_list, observance.subcycle)
            collect_text = _resolve_collect_text(db, propers_list)
            observances.append(
                {
                    "handle": observance.handle,
                    "title": observance.name or observance.alternative_name,
                    "priority": observance.priority,
                    "style": observance.style,
                    "subcycle": observance.subcycle,
                    "propers": propers_list,
                    "collect": str(markdown(collect_text)) if collect_text else None,
                    "acclamation": (
                        str(markdown(acclamation_text)) if acclamation_text else None
                    ),
                    "proper_preface": (
                        str(markdown(proper_preface_text))
                        if proper_preface_text
                        else None
                    ),
                    "lessons": {
                        "lesson_1": _format_lesson_reference(readings.get(1)),
                        "psalm": _format_lesson_reference(readings.get(2)),
                        "lesson_2": _format_lesson_reference(readings.get(3)),
                        "gospel": _format_lesson_reference(readings.get(5)),
                    },
                }
            )
        return jsonify({"date": raw_date, "season": season, "observances": observances})

    @bp.route("/<slug>")
    def page(slug):
        db = get_db()
        page = db.execute(
            "select title, content from pages where slug=? limit 1", (slug,)
        ).fetchone()
        if page:
            return render_template(
                "page.html", title=page["title"], content=page["content"]
            )
        return render_error("Page not found.", 404)

    @bp.route("/season")
    def season_from_date():
        raw_date = request.args.get("date", "")
        if not raw_date:
            return jsonify({"season": None})
        try:
            season = resolve_season(date.fromisoformat(raw_date))
        except ValueError:
            season = None
        return jsonify({"season": season})

    @bp.route("/observance")
    def observance_from_date():
        raw_date = request.args.get("date", "")
        handle = request.args.get("handle", "")
        if not raw_date:
            return jsonify(
                {
                    "title": None,
                    "handle": None,
                    "propers": [],
                    "season": None,
                    "options": [],
                    "default_handle": None,
                    "lesson_defaults": {},
                }
            )
        try:
            service_date = date.fromisoformat(raw_date)
        except ValueError:
            return jsonify(
                {
                    "title": None,
                    "handle": None,
                    "propers": [],
                    "season": None,
                    "options": [],
                    "default_handle": None,
                    "lesson_defaults": {},
                }
            )
        options = resolve_observance_options(service_date)
        observance = resolve_observance(service_date, handle) if options else None
        season = resolve_season(service_date)
        if not observance:
            return jsonify(
                {
                    "title": None,
                    "handle": None,
                    "propers": [],
                    "season": season,
                    "options": [],
                    "default_handle": None,
                    "lesson_defaults": {},
                }
            )
        title = observance.name or observance.alternative_name
        options_payload = [
            {
                "handle": option.handle,
                "title": option.name or option.alternative_name,
                "priority": option.priority,
            }
            for option in options
        ]
        return jsonify(
            {
                "title": title,
                "handle": observance.handle,
                "propers": list(observance.propers),
                "season": season,
                "subcycle": observance.subcycle,
                "options": options_payload,
                "default_handle": (
                    options_payload[0]["handle"] if options_payload else None
                ),
                "lesson_defaults": _resolve_lesson_references(
                    raw_date, observance.handle
                ),
            }
        )
