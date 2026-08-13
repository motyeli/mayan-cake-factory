"""FastAPI application factory.

Two middleware layers wrap every request: one assigns a correlation ID and
logs the outcome, the other applies security headers. Business logic lives in
app/services — route handlers stay thin on purpose (spec section 43).
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings, missing_credentials
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, correlation_id, get_logger, new_correlation_id
from app.core.supabase import supabase

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await supabase.start()
    settings = get_settings()
    logger.info(
        "backend starting",
        extra={
            "app_env": settings.app_env,
            "ai_mode": settings.ai_mode,
            "maps_provider": settings.maps_provider,
            "supabase_configured": supabase.configured,
            "missing_credentials": missing_credentials(),
        },
    )
    yield
    await supabase.close()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Tags each request so a customer report can be traced through the logs."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Correlation-ID")
        token = correlation_id.set(incoming or new_correlation_id())
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
        # Query strings can carry session tokens, so log the path only.
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Correlation-ID"] = correlation_id.get()
        correlation_id.reset(token)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if get_settings().is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        description=(
            "Backend for AI-assisted custom cake design and ordering. "
            "Prices, availability, feasibility and order status are computed "
            "deterministically; the language model never decides them."
        ),
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID"],
    )

    register_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["health"], summary="Liveness and dependency check")
    async def health() -> dict[str, object]:
        database = await supabase.ping()
        settings = get_settings()
        return {
            "status": "ok" if database == "ok" else "degraded",
            "environment": settings.app_env,
            "database": database,
            "ai_mode": settings.ai_mode,
            "maps_provider": settings.maps_provider,
            "missing_credentials": missing_credentials(),
        }

    return app


app = create_app()
