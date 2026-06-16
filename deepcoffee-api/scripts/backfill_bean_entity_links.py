"""一次性回填：给已有私有豆卡补建公共实体关联（幂等，可重复跑）。

阶段 3 上线后跑一次，让**历史**豆卡的 roaster_entity_id 等也指向公共实体——否则只有新建 /
编辑过的豆卡才有关联，老豆卡无法按实体聚合搜索。

用法（读 .env 的 DATABASE_URL）：
    cd deepcoffee-api && python -m scripts.backfill_bean_entity_links
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.models.tables import UserBeanCard
from app.repositories.beans import bean_repository


async def main() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = await session.execute(select(UserBeanCard).where(UserBeanCard.status == "active"))
        cards = list(rows.scalars().all())
        newly_linked = 0
        for card in cards:
            before = card.roaster_entity_id
            await bean_repository._link_entities(session, card)
            if card.roaster_entity_id and card.roaster_entity_id != before:
                newly_linked += 1
        await session.commit()
        print(f"回填完成：扫描 {len(cards)} 张豆卡，新关联 {newly_linked} 张的烘焙商实体。")


if __name__ == "__main__":
    asyncio.run(main())
