"""CLI：把 markdown 实体种子灌进公共实体库。

在 api 容器内运行（容器已带 DATABASE_URL 指向 Supabase）：

    python -m app.cli.seed_entities            # dry-run：只算计划、打印报告，不写库
    python -m app.cli.seed_entities --apply    # 真写库（请先看过 dry-run 报告）

设计见 ``app/services/entity_seed_importer``。默认 dry-run 是有意为之的安全闸。
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.services.entity_seed_importer import EntitySeedImporter


async def _run(apply: bool) -> str:
    settings = get_settings()
    importer = EntitySeedImporter(settings.resolved_knowledge_dir)
    sessionmaker = get_sessionmaker()
    try:
        async with sessionmaker() as session:
            report = await importer.run(session, dry_run=not apply)
            if apply:
                await session.commit()
            else:
                await session.rollback()
        return report.render()
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="把 markdown 实体种子灌进公共实体库")
    parser.add_argument(
        "--apply", action="store_true", help="真写库（默认 dry-run，只打印计划不写库）"
    )
    args = parser.parse_args()
    print(asyncio.run(_run(args.apply)))


if __name__ == "__main__":
    main()
