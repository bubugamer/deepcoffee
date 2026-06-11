from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, auth, beans, billing, brew, coffea, equipment, health, knowledge, proposals
from app.core.config import Settings, get_settings
from app.core.db import create_all
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.observability import init_observability
from app.services.bootstrap import seed_bootstrap_invite_code

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Ensure tables exist on startup (idempotent); best-effort so the app still
    # boots if the database is briefly unavailable.
    try:
        await create_all()
        await seed_bootstrap_invite_code(get_settings())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database schema init skipped: %s", exc)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    init_observability(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(billing.router, prefix=settings.api_prefix)
    app.include_router(brew.router, prefix=settings.api_prefix)
    app.include_router(beans.router, prefix=settings.api_prefix)
    app.include_router(equipment.router, prefix=settings.api_prefix)
    app.include_router(coffea.router, prefix=settings.api_prefix)
    app.include_router(knowledge.router, prefix=settings.api_prefix)
    app.include_router(proposals.router, prefix=settings.api_prefix)
    app.include_router(admin.router, prefix=settings.api_prefix)

    return app


app = create_app()
