from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(get_remote_address)


def init_rate_limiter(app):
    limiter.enabled = app.config.get("RATELIMIT_ENABLED", True)
    limiter.init_app(app)
