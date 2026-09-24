"""FastAPI application: routers, error format, request ids, security headers."""

from __future__ import annotations

import html
import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException
from redis.exceptions import RedisError

from app import db, errors, logging_setup, redis_client
from app.admin import routes as admin
from app.api import v1
from app.config import get_settings
from app.telegram import client as telegram_client
from app.telegram import webhook
from app.web import routes as web

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await db.dispose()
    await redis_client.close()
    if telegram_client._http is not None:
        await telegram_client._http.aclose()
        telegram_client._http = None


def _error_response(request: Request, exc: errors.AppError) -> JSONResponse:
    body = {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "request_id": getattr(request.state, "request_id", None),
            "retry_after_seconds": exc.retry_after,
            "fields": exc.fields,
            **exc.extra,
        }
    }
    headers = {"Cache-Control": "no-store"}
    if exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(body, status_code=exc.status, headers=headers)


def create_app() -> FastAPI:
    settings = get_settings()
    logging_setup.configure(settings.log_level)
    app = FastAPI(
        title="Future Fashion API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production_like else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production_like else "/openapi.json",
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if incoming.isalnum() and len(incoming) <= 40 else secrets.token_hex(8)
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/admin"):
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'"
            )
        route = request.scope.get("route")
        log.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": getattr(route, "path", "unmatched"),
                "status": response.status_code,
                "ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

    @app.exception_handler(errors.AppError)
    async def app_error(request: Request, exc: errors.AppError) -> Response:
        if request.url.path.startswith("/admin"):
            # Admin pages are HTML forms: show the message with a way back.
            return HTMLResponse(
                f"<p>{html.escape(exc.message)}</p><p><a href='javascript:history.back()'>Go back</a></p>",
                status_code=exc.status,
            )
        return _error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for item in exc.errors():
            location = [str(part) for part in item.get("loc", ()) if part not in ("body", "query", "header")]
            fields[".".join(location) or "request"] = "This value isn't valid."
        return _error_response(request, errors.ValidationFailed(fields=fields))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _error_response(request, errors.NotFound())
        if exc.status_code == 405:
            error = errors.AppError("Method not allowed.")
            error.status, error.code = 405, "METHOD_NOT_ALLOWED"
            return _error_response(request, error)
        return _error_response(request, errors.AppError())

    @app.exception_handler(OperationalError)
    @app.exception_handler(RedisError)
    async def dependency_down(request: Request, exc: Exception) -> JSONResponse:
        log.error("dependency unavailable", extra={"request_id": getattr(request.state, "request_id", None), "error": type(exc).__name__})
        return _error_response(request, errors.ServiceUnavailable())

    @app.exception_handler(DBAPIError)
    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", extra={"request_id": getattr(request.state, "request_id", None)})
        error = errors.AppError()
        error.status, error.code = 500, "INTERNAL_ERROR"
        return _error_response(request, error)

    app.include_router(v1.public)
    app.include_router(v1.router)
    app.include_router(webhook.router)
    app.include_router(web.router)
    admin.install(app)
    return app


app = create_app()
