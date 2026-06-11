"""Create all tables on the Supabase database (SUPABASE_DATABASE_URL in .env).

Usage (from deepcoffee-api/):
    ../.venv/bin/python -m scripts.create_tables_supabase

Only prints the host (never the password).
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.db import create_all_on_url, dispose_engine


async def main() -> None:
    settings = get_settings()
    url = settings.supabase_database_url
    if not url:
        raise SystemExit("SUPABASE_DATABASE_URL is not set in .env")

    parsed = urlsplit(url)
    print(f"Connecting to Supabase host: {parsed.hostname}:{parsed.port}")
    await create_all_on_url(url)
    await dispose_engine()
    print("Done. Tables created on Supabase (if not already present).")


if __name__ == "__main__":
    asyncio.run(main())
