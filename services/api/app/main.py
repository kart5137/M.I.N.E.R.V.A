from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.routers import (
    analytics,
    countries,
    detection,
    geo,
    intelligence,
    meta,
    models,
    surveillance,
)

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Epidemic Intelligence API",
        version=settings.version,
        description=(
            "Read-mostly API over stored surveillance data and model outputs. "
            "Analytical tool only; not medical or public-health guidance."
        ),
        docs_url="/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    register_error_handlers(app)
    app.include_router(meta.router, prefix=API_PREFIX)
    app.include_router(geo.router, prefix=API_PREFIX)
    app.include_router(surveillance.router, prefix=API_PREFIX)
    app.include_router(countries.router, prefix=API_PREFIX)
    app.include_router(analytics.router, prefix=API_PREFIX)
    app.include_router(models.router, prefix=API_PREFIX)
    app.include_router(detection.router, prefix=API_PREFIX)
    app.include_router(intelligence.router, prefix=API_PREFIX)
    return app


app = create_app()
