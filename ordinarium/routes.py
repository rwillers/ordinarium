import json
import uuid
from functools import wraps
from datetime import date

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    g,
    redirect,
    render_template,
    request,
    session,
    send_from_directory,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import ordinarium

from .db import get_db
from .liturgical_calendar import (
    resolve_observance,
    resolve_observance_options,
    resolve_season,
)

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


@bp.route("/health")
def health():
    return jsonify({"status": "ok"})


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("main.services"))
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not email or not password:
            error = "Email and password are required."
        else:
            user = get_user_by_email(email)
            if not user:
                error = "Invalid email or password."
            else:
                data = json.loads(user["data"]) if user["data"] else {}
                password_hash = data.get("password_hash")
                if not password_hash or not check_password_hash(
                    password_hash, password
                ):
                    error = "Invalid email or password."
        if not error and user:
            session.clear()
            session["user_id"] = user["id"]
            next_url = request.form.get("next") or request.args.get("next") or url_for(
                "main.services"
            )
            return redirect(next_url)
    if error:
        flash(error, "error")
    return render_template("login.html")


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if g.user:
        return redirect(url_for("main.services"))
    error = None
    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not first_name or not last_name or not email or not password:
            error = "All fields are required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif get_user_by_email(email):
            error = "An account with this email already exists."
        if not error:
            db = get_db()
            payload = {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "password_hash": generate_password_hash(password),
            }
            db.execute("insert into users (data) values (?)", (json.dumps(payload),))
            db.commit()
            user = get_user_by_email(email)
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("main.services"))
    if error:
        flash(error, "error")
    return render_template("signup.html")


def get_user_by_id(user_id):
    if not user_id:
        return None
    db = get_db()
    user = db.execute(
        "select id, first_name, last_name, email, data from users where id=? limit 1",
        (user_id,),
    ).fetchone()
    return user


def get_user_by_email(email):
    if not email:
        return None
    db = get_db()
    user = db.execute(
        "select id, first_name, last_name, email, data from users where email=? limit 1",
        (email,),
    ).fetchone()
    return user


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = get_user_by_id(user_id) if user_id else None


@bp.app_context_processor
def inject_user():
    return {"user": g.user}


def login_required(view):
    @wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("main.login", next=request.path))
        return view(**kwargs)
    return wrapped


def render_error(message, status_code=400):
    flash(message, "error")
    return render_template("page.html", title="Error", content=""), status_code


@bp.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("main.index"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    error = None
    user = get_user_by_id(g.user["id"])
    data = json.loads(user["data"]) if user and user["data"] else {}
    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not first_name or not last_name or not email:
            error = "Name and email are required."
        else:
            existing = get_user_by_email(email)
            if existing and existing["id"] != g.user["id"]:
                error = "An account with this email already exists."
        if password and len(password) < 8:
            error = "Password must be at least 8 characters."
        if not error:
            data.update(
                {
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                }
            )
            if password:
                data["password_hash"] = generate_password_hash(password)
            db = get_db()
            db.execute(
                "update users set data=? where id=?",
                (json.dumps(data), g.user["id"]),
            )
            db.commit()
            return redirect(url_for("main.account"))
    if error:
        flash(error, "error")
    return render_template(
        "account.html",
        first_name=user["first_name"] if user else "",
        last_name=user["last_name"] if user else "",
        email=user["email"] if user else "",
    )


# Main routes


@bp.route("/")
def index():
    return page("home")


def build_plan_context(service_id, rite):
    rite_slug = rite.replace(" ", "_").lower()
    db = get_db()
    saved_plan = db.execute(
        "select text_order, text_disabled, title, season, service_date, rite, data from services where id=? and user_id=? limit 1",
        (service_id, g.user["id"]),
    ).fetchone()
    saved_data = (
        json.loads(saved_plan["data"]) if saved_plan and saved_plan["data"] else {}
    )
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
    observance_options = []
    observance_title = ""
    observance_handle = saved_data.get("observance_handle")
    if saved_plan and saved_plan["service_date"]:
        try:
            service_date = date.fromisoformat(saved_plan["service_date"])
        except ValueError:
            service_date = None
        if service_date:
            options = resolve_observance_options(service_date)
            if options:
                observance_options = []
                selected_handle = observance_handle
                if selected_handle and not any(
                    option.handle == selected_handle for option in options
                ):
                    selected_handle = None
                if not selected_handle:
                    selected_handle = options[0].handle
                for index, option in enumerate(options):
                    title = option.name or option.alternative_name
                    observance_options.append(
                        {
                            "handle": option.handle,
                            "title": title,
                            "is_default": index == 0,
                            "selected": option.handle == selected_handle,
                        }
                    )
                observance_title = next(
                    (
                        option["title"]
                        for option in observance_options
                        if option["selected"]
                    ),
                    "",
                )

    service_data = {
        "season": saved_plan["season"] if saved_plan else "",
        "service_date": saved_plan["service_date"] if saved_plan else "",
        "rite": saved_plan["rite"] if saved_plan and saved_plan["rite"] else rite,
    }
    return {
        "rite": rite,
        "rite_slug": rite_slug,
        "ordinaries": ordinaries,
        "service_id": service_id,
        "service": service_data,
        "observance_options": observance_options,
        "observance_title": observance_title,
        "can_delete": bool(saved_plan and saved_plan["service_date"]),
        "can_share": bool(saved_plan),
    }


@bp.route("/service/<int:service_id>")
@login_required
def service(service_id, rite="Renewed Ancient Text"):
    db = get_db()
    existing_owner = db.execute(
        "select user_id from services where id=? limit 1", (service_id,)
    ).fetchone()
    if existing_owner and existing_owner["user_id"] != g.user["id"]:
        return render_error("Service not found.", 404)
    context = build_plan_context(service_id, rite)
    return render_template("service.html", **context)


@bp.route("/service")
@login_required
def service_missing_id():
    return render_error(
        "Service ID required. Open a service from the Services list.", 400
    )


@bp.route("/services")
@login_required
def services():
    db = get_db()
    today = date.today().isoformat()
    current_services = db.execute(
        "select id, title, service_date, data from services where user_id=? and service_date is not null and service_date >= ? order by service_date asc",
        (g.user["id"], today),
    ).fetchall()
    past_services = db.execute(
        "select id, title, service_date, data from services where user_id=? and service_date is not null and service_date < ? order by service_date desc",
        (g.user["id"], today),
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
            title = None
            saved_data = json.loads(service["data"]) if service["data"] else {}
            observance_handle = saved_data.get("observance_handle")
            if service["service_date"]:
                try:
                    observance = resolve_observance(
                        date.fromisoformat(service["service_date"]),
                        observance_handle,
                    )
                except ValueError:
                    observance = None
                if observance:
                    title = observance.name or observance.alternative_name
            if not title:
                title = service["title"]
            formatted.append(
                {
                    "id": service["id"],
                    "title": title or "Untitled Service",
                    "service_date": service["service_date"],
                    "display_date": display_date,
                }
            )
        return formatted

    return render_template(
        "services.html",
        current_services=format_services(current_services),
        past_services=format_services(past_services),
    )


@bp.route("/services/new")
@login_required
def services_new():
    db = get_db()
    next_id = db.execute(
        "select coalesce(max(id), 0) + 1 as next_id from services"
    ).fetchone()
    return redirect(url_for("main.service", service_id=next_id["next_id"]))


@bp.route("/service/<int:service_id>/delete", methods=["POST"])
@login_required
def service_delete(service_id):
    db = get_db()
    db.execute(
        "delete from services where id=? and user_id=?", (service_id, g.user["id"])
    )
    db.commit()
    return redirect(url_for("main.services"))


def load_service_for_text(service_id, user_id=None):
    if not service_id:
        return None, {}
    db = get_db()
    if user_id:
        saved_service = db.execute(
            "select text_order, text_disabled, season, rite, service_date, data from services where id=? and user_id=? limit 1",
            (service_id, user_id),
        ).fetchone()
    else:
        saved_service = db.execute(
            "select text_order, text_disabled, season, rite, service_date, data from services where id=? limit 1",
            (service_id,),
        ).fetchone()
    saved_data = (
        json.loads(saved_service["data"])
        if saved_service and saved_service["data"]
        else {}
    )
    return saved_service, saved_data


def render_text_page(service_id, saved_service, saved_data):
    if not saved_service:
        return render_error("Service ID required to generate text.", 400)
    db = get_db()

    # Update not to be hard coded:
    title = "<!--<small>The Order for the Administration of</small>  \nThe Lord’s Supper  \n<small>*or*</small>  \nHoly Communion,  \n<small>Commonly Called</small>  \n-->The Holy Eucharist"

    if not saved_service["rite"]:
        return render_error("Service rite is required to generate text.", 400)
    rite_name = saved_service["rite"]
    rite = db.execute(
        "select distinct filter_content from texts where type=? and filter_type=? and filter_content=? limit 1",
        ("ordinarium", "rite", rite_name),
    ).fetchone()
    if not rite:
        return render_error("Rite not found.", 404)

    disabled_json = "[]"
    if saved_service and saved_service["text_disabled"]:
        disabled_json = saved_service["text_disabled"]

    if saved_service["text_order"]:
        ordinaries = db.execute(
            'select texts.title, texts.text from texts join json_each(?) saved_order on texts.id=saved_order.value left join json_each(?) saved_disabled on texts.id=saved_disabled.value where texts.type=? and texts.filter_type=? and texts.filter_content=? and saved_disabled.value is null order by saved_order.key;',
            (
                saved_service["text_order"],
                disabled_json,
                "ordinarium",
                "rite",
                rite_name,
            ),
        ).fetchall()
    else:
        ordinaries = db.execute(
            "select texts.title, texts.text from texts left join json_each(?) saved_disabled on texts.id=saved_disabled.value where texts.type=? and texts.filter_type=? and texts.filter_content=? and saved_disabled.value is null order by default_order;",
            (disabled_json, "ordinarium", "rite", rite_name),
        ).fetchall()
    if not ordinaries:
        return render_error("Content not found.", 404)

    season = request.args.get("season", "")
    if service_id:
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
    observance = None
    propers_list = []
    if saved_service and saved_service["service_date"]:
        try:
            observance = resolve_observance(
                date.fromisoformat(saved_service["service_date"]),
                saved_data.get("observance_handle"),
            )
        except ValueError:
            observance = None
    if observance:
        propers_list = list(observance.propers)

    collect_text = None
    if propers_list:
        propers_json = json.dumps(propers_list)
        collect_text = db.execute(
            "select texts.text from texts join json_each(?) propers on texts.filter_content=propers.value where texts.type=? and texts.filter_type=? order by propers.key, texts.default_order limit 1",
            (propers_json, "collect", "proper"),
        ).fetchone()

    lessons = []
    if propers_list:
        propers_json = json.dumps(propers_list)
        lessons = db.execute(
            "select texts.data from texts join json_each(?) propers on texts.filter_content=propers.value where texts.type=? and texts.filter_type=? order by propers.key, texts.default_order",
            (propers_json, "lesson", "proper"),
        ).fetchall()

    subcycle = observance.subcycle if observance else None
    readings = {}
    if lessons:
        for row in lessons:
            lesson = json.loads(row["data"])
            if lesson.get("optional"):
                continue
            lesson_subcycles = lesson.get("subcycles") or []
            if lesson_subcycles and subcycle and subcycle not in lesson_subcycles:
                continue
            reading_number = lesson.get("reading")
            if reading_number in readings:
                continue
            readings[reading_number] = lesson

    def format_reference(lesson):
        if not lesson:
            return None
        reference_short = lesson.get("reference_short")
        if reference_short and reference_short.strip() == "_":
            reference_short = None
        reference = reference_short or lesson.get("reference_long")
        if not reference:
            return None
        book_name = lesson.get("book_name") or lesson.get("book")
        if not book_name:
            return reference
        return f"{book_name} ({reference})"

    propers = {
        "acclamation": (
            acclamation["text"] if acclamation else "*Error: No acclamation found.*"
        ),
        "collect_of_the_day": (
            collect_text["text"]
            if collect_text
            else "*Error: No collect found for this date.*"
        ),
        "lesson_1_reference": format_reference(readings.get(1))
        or "*Error: No first lesson found.*",
        "psalm_reference": format_reference(readings.get(2))
        or "*Error: No psalm found.*",
        "lesson_2_reference": format_reference(readings.get(3))
        or "*Error: No second lesson found.*",
        "gospel_reference": format_reference(readings.get(5))
        or "*Error: No gospel found.*",
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
    service_title = observance.name or observance.alternative_name if observance else ""
    return render_template(
        "text.html",
        title=title,
        rite=rite_name,
        service_title=service_title,
        ordinaries=ordinaries,
        **propers,
    )


@bp.route("/text/<int:service_id>")
@login_required
def text(service_id):
    saved_service, saved_data = load_service_for_text(service_id, g.user["id"])
    return render_text_page(service_id, saved_service, saved_data)


@bp.route("/share/<share_uuid>")
def shared_text(share_uuid):
    db = get_db()
    share = db.execute(
        "select service_id from service_shares where share_uuid=? limit 1",
        (share_uuid,),
    ).fetchone()
    if not share:
        return render_error("Share link not found.", 404)
    saved_service, saved_data = load_service_for_text(share["service_id"])
    if not saved_service:
        return render_error("Service not found.", 404)
    return render_text_page(share["service_id"], saved_service, saved_data)


@bp.route("/service/<int:service_id>/share", methods=["POST"])
@login_required
def service_share(service_id):
    db = get_db()
    existing_owner = db.execute(
        "select user_id from services where id=? limit 1", (service_id,)
    ).fetchone()
    if not existing_owner or existing_owner["user_id"] != g.user["id"]:
        return render_error("Service not found.", 404)
    existing_share = db.execute(
        "select share_uuid from service_shares where service_id=? limit 1",
        (service_id,),
    ).fetchone()
    if existing_share:
        share_uuid = existing_share["share_uuid"]
        created = False
    else:
        share_uuid = str(uuid.uuid4())
        db.execute(
            "insert into service_shares (service_id, share_uuid) values (?, ?)",
            (service_id, share_uuid),
        )
        db.commit()
        created = True
    share_url = url_for("main.shared_text", share_uuid=share_uuid, _external=True)
    return jsonify({"share_uuid": share_uuid, "share_url": share_url, "created": created})


@bp.route("/persist/service", methods=["POST"])
@login_required
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
        "select data from services where id=? and user_id=? limit 1",
        (service_id, g.user["id"]),
    ).fetchone()
    other_owner = None
    if not existing:
        other_owner = db.execute(
            "select id from services where id=? limit 1", (service_id,)
        ).fetchone()
    if other_owner:
        return render_error("Service not found.", 404)
    existing_data = (
        json.loads(existing["data"]) if existing and existing["data"] else {}
    )
    payload = {
        "user_id": g.user["id"],
        "title": existing_data.get("title"),
        "rite": existing_data.get("rite", "Renewed Ancient Text"),
        "season": None,
        "service_date": existing_data.get("service_date"),
        "observance_handle": existing_data.get("observance_handle"),
    }
    payload.update(
        {
            "rite": normalize_value(request.form.get("rite")) or payload["rite"],
            "service_date": normalize_value(request.form.get("service_date"))
            or payload["service_date"],
            "text_order": order_json,
            "text_disabled": disabled_json,
            "observance_handle": normalize_value(
                request.form.get("observance_handle")
            ),
        }
    )
    observance = None
    if payload["service_date"]:
        try:
            observance = resolve_observance(
                date.fromisoformat(payload["service_date"]),
                payload["observance_handle"],
            )
        except ValueError:
            observance = None
        if observance:
            payload["observance_handle"] = observance.handle
    if observance:
        payload["title"] = observance.name or observance.alternative_name or ""
    if not payload["service_date"]:
        context = build_plan_context(service_id, payload["rite"])
        context["service"]["service_date"] = payload["service_date"] or ""
        flash("Service date is required.", "error")
        return render_template("service.html", **context), 400
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
    action = request.form.get("action", "")
    if action == "generate":
        return redirect(url_for("main.text", service_id=service_id))
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
    if not raw_date:
        return jsonify(
            {
                "title": None,
                "handle": None,
                "propers": [],
                "season": None,
                "options": [],
                "default_handle": None,
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
            }
        )
    options = resolve_observance_options(service_date)
    observance = options[0] if options else None
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
            "default_handle": options_payload[0]["handle"]
            if options_payload
            else None,
        }
    )
