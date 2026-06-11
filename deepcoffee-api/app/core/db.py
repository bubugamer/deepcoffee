from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _normalize_async_url(url: str) -> str:
    """Ensure the URL uses the asyncpg driver."""
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def _connect_args(url: str) -> dict:
    """Connect args: enforce SSL for Supabase; local / Docker-internal Postgres stays plaintext.

    asyncpg uses the ``ssl`` arg (not libpq ``sslmode``); ``require`` encrypts without
    strict CA verification (fine for beta; swap to a CA context for verify-full).
    Only Supabase hosts get SSL — the bundled `postgres:16` (localhost / `db` service)
    has no TLS, so requiring SSL there would break the connection.
    """
    args: dict = {}
    if "supabase" in url:
        args["ssl"] = "require"
        args["timeout"] = 20
    return args


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        settings = settings or get_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not configured.")
        url = _normalize_async_url(settings.database_url)
        extra: dict = {}
        if os.environ.get("DEEPCOFFEE_DB_NULLPOOL"):
            # Tests drive the app with a sync TestClient across multiple event loops;
            # NullPool avoids reusing asyncpg connections bound to a different loop.
            extra["poolclass"] = NullPool
        _engine = create_async_engine(
            url,
            pool_pre_ping=True,
            future=True,
            connect_args=_connect_args(url),
            **extra,
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async DB session with commit/rollback handling."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all() -> None:
    """Create all tables. Used for local dev and first-time Supabase setup."""
    from app import models  # noqa: F401  (register models on Base.metadata)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def create_all_on_url(url: str) -> None:
    """Create all tables on a specific URL (one-off, e.g. Supabase) without touching
    the global engine used for the running app."""
    from app import models  # noqa: F401  (register models on Base.metadata)

    norm = _normalize_async_url(url)
    engine = create_async_engine(norm, pool_pre_ping=True, connect_args=_connect_args(norm))
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
