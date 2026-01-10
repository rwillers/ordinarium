from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
import json

import ordinarium

from .db import get_db

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


@bp.route("/plan")
def plan(rite="Renewed Ancient Text"):
    rite_slug = rite.replace(" ", "_").lower()

    db = get_db()

    saved_plan = db.execute(
        "select text_order, text_disabled from services where id=? limit 1", (1,)
    ).fetchone()
    if saved_plan:
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
    return render_template(
        "plan.html",
        user=get_user(),
        rite=rite,
        rite_slug=rite_slug,
        ordinaries=ordinaries,
    )


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

    season = request.args.get("season", "")

    # Move propers selection to class
    acclamation = db.execute(
        "select text from texts where type=? and filter_type=? and filter_content=? order by random() limit 1",
        ("acclamation", "season", season),
    ).fetchone()
    offertory_sentence = db.execute(
        "select text from texts where type=? order by random() limit 1",
        ("offertory_sentence",),
    ).fetchone()
    proper_preface = db.execute(
        "select text from texts where type=? and filter_type=? and filter_content=? order by random() limit 1",
        ("proper_preface", "season", season),
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
    order = request.form.get("ids", "").split(",") if request.form.get("ids") else []
    order_json = "[" + ",".join(order) + "]"
    disabled = (
        request.form.get("disabled", "").split(",")
        if request.form.get("disabled")
        else []
    )
    disabled_json = "[" + ",".join(disabled) + "]"

    payload = {
        "user_id": 1,
        "title": "First Sunday of Christmas",
        "rite": "Renewed Ancient Text",
        "text_order": order_json,
        "text_disabled": disabled_json,
    }

    db = get_db()
    db.execute("update services set data=? where id=?", (json.dumps(payload), 1))
    db.commit()
    # flash('Service saved.')

    return redirect(url_for("main.plan"))


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
