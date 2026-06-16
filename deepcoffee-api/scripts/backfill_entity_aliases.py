"""一次性回填：给所有 active 公共实体补建自动别名（幂等，可重复跑）。

阶段 1 消歧上线后跑一次，让**现有**实体（如「Captain George / 乔治队长」）也能被
别名 / 形态 key 匹配命中——否则只有新建实体才有自动别名。

用法（读 .env 的 DATABASE_URL）：
    cd deepcoffee-api && python -m scripts.backfill_entity_aliases
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.models.tables import PublicEntity
from app.repositories.entities import entity_repository


async def main() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = await session.execute(select(PublicEntity).where(PublicEntity.status == "active"))
        entities = list(rows.scalars().all())
        for e in entities:
            await entity_repository.register_aliases(session, e.id, e.canonical_name)
        await session.commit()
        print(f"回填完成：已为 {len(entities)} 个 active 实体补建自动别名。")


if __name__ == "__main__":
    asyncio.run(main())
