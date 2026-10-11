"""
app/core/error_handlers.py
Global error handlers formatting all error responses consistently per SPEC 12.1:
{"error": {"code": "...", "message": "...", "request_id": "..."}}
"""
from __future__ import annotations

import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from app.core.exceptions import AppError
from app.core.logging import get_request_id

log = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        req_id = get_request_id()
        content = {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": req_id,
            }
        }
        return JSONResponse(status_code=exc.http_status, content=content)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        req_id = get_request_id()
        # Strictly strip 'input' per SPEC 12.1 (FastAPI echoes input which could contain password/OTP)
        issues = []
        for err in exc.errors():
            issue = {
                "loc": list(err.get("loc", [])),
                "msg": str(err.get("msg", "")),
            }
            issues.append(issue)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_FAILED",
                    "message": "Request validation failed",
                    "details": issues,
                    "request_id": req_id,
                }
            },
        )

    @app.exception_handler(OperationalError)
    async def db_operational_error_handler(request: Request, exc: OperationalError):
        req_id = get_request_id()
        log.exception("Database operational error [request_id=%s]: %s", req_id, exc)
        if "database is locked" in str(exc).lower():
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "TEMPORARILY_UNAVAILABLE",
                        "message": "Database is locked. Please retry.",
                        "request_id": req_id,
                    }
                },
            )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal database error",
                    "request_id": req_id,
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
        req_id = get_request_id()
        log.exception("SQLAlchemy error [request_id=%s]: %s", req_id, exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal database error",
                    "request_id": req_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        req_id = get_request_id()
        log.exception("Unhandled error [request_id=%s]: %s", req_id, exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error",
                    "request_id": req_id,
                }
            },
        )
