from flask import flash, render_template


def render_error(message, status_code=400):
    flash(message, "error")
    return render_template("page.html", title="Error", content=""), status_code
