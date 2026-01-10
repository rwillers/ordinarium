import json
from datetime import date

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

import ordinarium

from .db import get_db
from .liturgical_calendar import resolve_season

bp = Blueprint("main", __name__)


# Utility functions


@bp.route("/favicon.ico")
def favicon():
    if current_app.static_folder is None:
        return "", 404
    return send_from_directory(
        current_app.static_folder,
        "images/favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


def get_user(email="ryanwillers@gmail.com"):
    db = get_db()
    user = db.execute(
        "select id, first_name, last_name, email from users where email=? limit 1",
        (email,),
    ).fetchone()
    return user


# Main routes


@bp.route("/")
def index():
    return page("home")


@bp.route("/service/<int:service_id>")
def service(service_id, rite="Renewed Ancient Text"):
    rite_slug = rite.replace(" ", "_").lower()

    db = get_db()

    saved_plan = db.execute(
        "select text_order, text_disabled, title, season, service_date, rite from services where id=? limit 1",
        (service_id,),
    ).fetchone()
    if saved_plan and saved_plan["text_order"]:
        ordinaries = db.execute(
            'select texts.id, texts.default_order, texts.title, texts.detailed_title, texts.text, saved_order.value, saved_disabled.value as "disabled" from texts left join json_each(?) saved_order on texts.id=saved_order.value left join json_each(?) saved_disabled on texts.id=saved_disabled.value where texts.type=? and texts.filter_type=? and texts.filter_content=? order by saved_order.key',
            (
                saved_plan["text_order"],
                saved_plan["text_disabled"],
                "ordinarium",
                "rite",
                rite,
            ),
        ).fetchall()
    else:
        ordinaries = db.execute(
            "select id, default_order, title, detailed_title, text from texts where type=? and filter_type=? and filter_content=? order by default_order",
            ("ordinarium", "rite", rite),
        ).fetchall()
    service_data = {
        "title": saved_plan["title"] if saved_plan else "",
        "season": saved_plan["season"] if saved_plan else "",
        "service_date": saved_plan["service_date"] if saved_plan else "",
        "rite": saved_plan["rite"] if saved_plan and saved_plan["rite"] else rite,
    }
    return render_template(
        "plan.html",
        user=get_user(),
        rite=rite,
        rite_slug=rite_slug,
        ordinaries=ordinaries,
        service_id=service_id,
        service=service_data,
    )


@bp.route("/service")
def service_missing_id():
    return (
        render_template(
            "page.html",
            title="Error",
            content="Service ID required. Open a service from the Services list.",
        ),
        400,
    )


@bp.route("/services")
def services():
    user = get_user()
    if not user:
        return render_template("page.html", title="Error", content="User not found"), 404

    db = get_db()
    today = date.today().isoformat()
    current_services = db.execute(
        "select id, title, service_date from services where user_id=? and service_date is not null and service_date >= ? order by service_date asc",
        (user["id"], today),
    ).fetchall()
    past_services = db.execute(
        "select id, title, service_date from services where user_id=? and service_date is not null and service_date < ? order by service_date desc",
        (user["id"], today),
    ).fetchall()
    def format_services(services):
        formatted = []
        for service in services:
            display_date = service["service_date"]
            try:
                parsed = date.fromisoformat(service["service_date"])
                display_date = f"{parsed.month}/{parsed.day}/{parsed.year}"
            except (TypeError, ValueError):
                pass
            formatted.append(
                {
                    "id": service["id"],
                    "title": service["title"],
                    "service_date": service["service_date"],
                    "display_date": display_date,
                }
            )
        return formatted

    return render_template(
        "services.html",
        user=user,
        current_services=format_services(current_services),
        past_services=format_services(past_services),
    )


@bp.route("/services/new")
def services_new():
    user = get_user()
    if not user:
        return render_template("page.html", title="Error", content="User not found"), 404

    db = get_db()
    next_id = db.execute("select coalesce(max(id), 0) + 1 as next_id from services").fetchone()
    return redirect(url_for("main.service", service_id=next_id["next_id"]))


@bp.route("/text/<rite_slug>")
def text(rite_slug):
    if not rite_slug:
        return (
            render_template("page.html", title="Error", content="No rite indicated"),
            404,
        )

    db = get_db()

    # Update not to be hard coded:
    title = "<!--<small>The Order for the Administration of</small>  \nThe Lord’s Supper  \n<small>*or*</small>  \nHoly Communion,  \n<small>Commonly Called</small>  \n-->The Holy Eucharist"

    rite_name = rite_slug.replace("_", " ").title()
    rite = db.execute(
        "select distinct filter_content from texts where type=? and filter_type=? and filter_content=? limit 1",
        ("ordinarium", "rite", rite_name),
    ).fetchone()
    if not rite:
        return (
            render_template("page.html", title="Error", content="Rite not found"),
            404,
        )

    ids = request.args.get("ids", "").split(",") if request.args.get("ids") else []
    if ids:
        ids_json = "[" + ",".join(ids) + "]"
        ordinaries = db.execute(
            "select title, text from texts join json_each(?) ids on texts.id=ids.value where texts.type=? and texts.filter_type=? and texts.filter_content=? order by ids.key;",
            (ids_json, "ordinarium", "rite", rite_name),
        ).fetchall()
    else:
        ordinaries = db.execute(
            "select title, text from texts where type=? and filter_type=? and filter_content=? order by default_order;",
            ("ordinarium", "rite", rite_name),
        ).fetchall()
    if not ordinaries:
        return (
            render_template("page.html", title="Error", content="Content not found"),
            404,
        )

    service_id = request.args.get("service_id")
    season = request.args.get("season", "")
    if service_id:
        try:
            service_id = int(service_id)
        except (TypeError, ValueError):
            service_id = None
    if service_id:
        saved_service = db.execute(
            "select season from services where id=? limit 1", (service_id,)
        ).fetchone()
        if saved_service and saved_service["season"]:
            season = saved_service["season"]

    # Move propers selection to class
    acclamation = None
    if season:
        acclamation = db.execute(
            "select text from texts where type=? and filter_type=? and filter_content=? order by random() limit 1",
            ("acclamation", "season", season),
        ).fetchone()
    if not acclamation:
        acclamation = db.execute(
            "select text from texts where type=? and ((filter_type=? and filter_content=?) or (filter_type=? and filter_content=?)) order by random() limit 1",
            ("acclamation", "other", "At Any Time", "day", "The Lord’s Day"),
        ).fetchone()
    offertory_sentence = db.execute(
        "select text from texts where type=? order by random() limit 1",
        ("offertory_sentence",),
    ).fetchone()
    proper_preface = None
    if season:
        proper_preface = db.execute(
            "select text from texts where type=? and filter_type=? and filter_content=? order by random() limit 1",
            ("proper_preface", "season", season),
        ).fetchone()
    if not proper_preface:
        proper_preface = db.execute(
            "select text from texts where type=? and ((filter_type=? and filter_content=?) or (filter_type=? and filter_content=?)) order by random() limit 1",
            ("proper_preface", "other", "At Any Time", "day", "The Lord’s Day"),
        ).fetchone()
    propers = {
        "acclamation": (
            acclamation["text"] if acclamation else "*Error: No acclamation found.*"
        ),
        "collect_of_the_day": "Almighty God, you have poured upon us the new light of your incarnate Word: Grant that this light, kindled in our hearts, may shine forth in our lives; through Jesus Christ our Lord, who lives and reigns with you in the unity of the Holy Spirit, one God, now and for ever. **Amen.**",
        "lesson_1_reference": "Isaiah (61:10–62:5)",
        "psalm_reference": "Psalm (147:12-20)",
        "lesson_2_reference": "Galations (3:23–4:7)",
        "gospel_reference": "John (1:1–18)",
        "offertory_sentence": (
            offertory_sentence["text"]
            if offertory_sentence
            else "*Error: No offertory sentence found.*"
        ),
        "proper_preface": (
            proper_preface["text"]
            if proper_preface
            else "*Error: No proper preface found.*"
        ),
    }
    return render_template(
        "text.html", title=title, rite=rite_name, ordinaries=ordinaries, **propers
    )


@bp.route("/persist/service", methods=["POST"])
def persist_service():
    def normalize_value(value):
        if value is None:
            return None
        value = value.strip()
        return value or None

    service_id = request.form.get("service_id", 1)
    try:
        service_id = int(service_id)
    except (TypeError, ValueError):
        service_id = 1

    order = request.form.get("ids", "").split(",") if request.form.get("ids") else []
    order_json = "[" + ",".join(order) + "]"
    disabled = (
        request.form.get("disabled", "").split(",")
        if request.form.get("disabled")
        else []
    )
    disabled_json = "[" + ",".join(disabled) + "]"

    db = get_db()
    existing = db.execute(
        "select data from services where id=? limit 1", (service_id,)
    ).fetchone()
    existing_data = (
        json.loads(existing["data"]) if existing and existing["data"] else {}
    )
    payload = {
        "user_id": existing_data.get("user_id", 1),
        "title": existing_data.get("title", "Untitled Service"),
        "rite": existing_data.get("rite", "Renewed Ancient Text"),
        "season": None,
        "service_date": existing_data.get("service_date"),
    }
    payload.update(
        {
            "user_id": normalize_value(request.form.get("user_id"))
            or payload["user_id"],
            "title": normalize_value(request.form.get("title")) or payload["title"],
            "rite": normalize_value(request.form.get("rite")) or payload["rite"],
            "service_date": normalize_value(request.form.get("service_date"))
            or payload["service_date"],
            "text_order": order_json,
            "text_disabled": disabled_json,
        }
    )
    if payload["service_date"]:
        try:
            payload["season"] = resolve_season(
                date.fromisoformat(payload["service_date"])
            )
        except ValueError:
            payload["season"] = None
    else:
        payload["season"] = None

    if existing:
        db.execute(
            "update services set data=? where id=?",
            (json.dumps(payload), service_id),
        )
    else:
        db.execute(
            "insert into services (id, data) values (?, ?)",
            (service_id, json.dumps(payload)),
        )
    db.commit()
    # flash('Service saved.')

    return redirect(url_for("main.service", service_id=service_id))


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
    else:
        return (
            render_template("page.html", title="Error", content="Page not found"),
            404,
        )


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
