from flask import Blueprint

from .account_routes import register_account_routes
from .admin_routes import register_admin_routes
from .auth_session import register_user_context
from .integrations_routes import register_integration_routes
from .login_routes import register_login_routes
from .page_routes import register_page_routes
from .password_reset_routes import register_password_reset_routes
from .service_pco_routes import register_service_pco_routes
from .service_routes import register_service_routes
from .settings_routes import register_settings_routes
from .text_routes import register_text_routes
from .user_store import create_password_reset_token

bp = Blueprint("main", __name__)

register_user_context(bp)
register_login_routes(bp)
register_password_reset_routes(bp)
register_account_routes(bp)
register_settings_routes(bp)
register_admin_routes(bp)
register_service_routes(bp)
register_service_pco_routes(bp)
register_integration_routes(bp)
register_text_routes(bp)
register_page_routes(bp)

__all__ = ["bp", "create_password_reset_token"]
