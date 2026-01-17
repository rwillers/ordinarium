import os

from ordinarium import create_app


app = create_app()

def _debug_enabled():
    return (
        os.getenv("ORDINARIUM_DEBUG") == "1"
        or os.getenv("FLASK_DEBUG") == "1"
        or os.getenv("FLASK_ENV") == "development"
    )


if __name__ == "__main__":
    app.run(debug=_debug_enabled())
