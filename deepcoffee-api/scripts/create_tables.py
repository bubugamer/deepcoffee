"""Create all database tables from the ORM models.

Usage (from deepcoffee-api/):
    ../.venv/bin/python -m scripts.create_tables

Reads DATABASE_URL from environment / .env. Safe to run repeatedly
(uses CREATE TABLE IF NOT EXISTS semantics).
"""

from __future__ import annotations

import asyncio

from app.core.db import create_all, dispose_engine, get_settings


async def main() -> None:
    settings = get_settings()
    print(f"Creating tables on: {settings.database_url}")
    await create_all()
    await dispose_engine()
    print("Done. All tables created (if not already present).")


if __name__ == "__main__":
    asyncio.run(main())
