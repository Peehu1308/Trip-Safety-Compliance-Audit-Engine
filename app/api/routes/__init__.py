"""
app/api/routes
API route registration package.
"""
from app.api.routes.auth import router as auth_router
from app.api.routes.trips import router as trips_router
from app.api.routes.gps import router as gps_router
from app.api.routes.events import router as events_router
from app.api.routes.violations import router as violations_router
from app.api.routes.audit import router as audit_router
from app.api.routes.ops import router as ops_router

__all__ = [
    "auth_router",
    "trips_router",
    "gps_router",
    "events_router",
    "violations_router",
    "audit_router",
    "ops_router",
]
