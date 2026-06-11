from __future__ import annotations

import logging

from app.core.config import Settings

logger = logging.getLogger(__name__)


def init_observability(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
    except Exception:
        logger.warning("Sentry DSN configured, but sentry-sdk could not be imported.")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.app_version,
        integrations=[FastApiIntegration()],
    )
