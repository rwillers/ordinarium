from .service_custom_routes import register_service_custom_routes
from .service_overview_routes import register_service_overview_routes
from .service_persist_routes import register_service_persist_routes
from .service_share_routes import register_service_share_routes
from .service_template_routes import register_service_template_routes


def register_service_routes(bp):
    register_service_overview_routes(bp)
    register_service_template_routes(bp)
    register_service_share_routes(bp)
    register_service_custom_routes(bp)
    register_service_persist_routes(bp)
