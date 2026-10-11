"""
app/main.py
FastAPI application factory, middleware, exception handlers, and routing per SPEC 11 & 12.
"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import request_id_ctx, PIIFilter, JSONFormatter
from app.core.error_handlers import register_error_handlers
from app.core.metrics import http_requests_total
from app.api.routes.auth import router as auth_router
from app.api.routes.trips import router as trips_router
from app.api.routes.gps import router as gps_router
from app.api.routes.events import router as events_router
from app.api.routes.violations import router as violations_router
from app.api.routes.audit import router as audit_router
from app.api.routes.ops import router as ops_router

# Configure root logger with PIIFilter and JSONFormatter
logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
handler.addFilter(PIIFilter())
logger.handlers = [handler]
logger.setLevel(logging.INFO)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_ctx.set(req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx.reset(token)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        route = request.scope.get("route")
        route_template = route.path if route and hasattr(route, "path") else "unmatched"
        http_requests_total.labels(
            method=request.method,
            route=route_template,
            status=str(response.status_code),
        ).inc()
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: log a warning if default secrets are used
    if "dev" in settings.JWT_SECRET or "dev" in settings.OTP_SECRET:
        logging.getLogger(__name__).warning(
            "Security Notice: Application is running with default development secrets!"
        )
    yield


app = FastAPI(
    title="MoveInSync Transport Safety & Compliance Engine",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware (outer-to-inner: RequestId wraps Metrics wraps router)
app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestIdMiddleware)

# Error handlers per SPEC 12.1
register_error_handlers(app)

# Include routers
app.include_router(auth_router)
app.include_router(trips_router)
app.include_router(gps_router)
app.include_router(events_router)
app.include_router(violations_router)
app.include_router(audit_router)
app.include_router(ops_router)
