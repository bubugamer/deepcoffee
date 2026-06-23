"""一次性回填：给已有私有豆卡重跑公共实体关联（幂等，可重复跑）。

让**历史**豆卡的 roaster_entity_id / origin_entity_id 等重新指向当前公共实体库——否则
只有新建 / 编辑过的豆卡才有关联，且实体库改了别名 / 合并后老豆卡的关联会陈旧。

默认 dry-run 只打印「哪张卡的哪个 *_entity_id 会变」；确认后加 --apply 才写库。

用法（读 .env 的 DATABASE_URL）：
    cd deepcoffee-api && python -m scripts.backfill_bean_entity_links            # dry-run
    cd deepcoffee-api && python -m scripts.backfill_bean_entity_links --apply    # 写库
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.models.tables import UserBeanCard
from app.repositories.beans import bean_repository

_ENTITY_ATTRS = [
    "roaster_entity_id",
    "roaster_product_entity_id",
    "origin_entity_id",
    "process_entity_id",
    "coffee_source_entity_id",
    "green_bean_merchant_entity_id",
    "green_bean_product_entity_id",
]


async def main(apply: bool) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = await session.execute(select(UserBeanCard).where(UserBeanCard.status == "active"))
        cards = list(rows.scalars().all())
        changed = 0
        for card in cards:
            before = {attr: getattr(card, attr) for attr in _ENTITY_ATTRS}
            await bean_repository._link_entities(session, card)
            diff = {attr: (before[attr], getattr(card, attr)) for attr in _ENTITY_ATTRS if before[attr] != getattr(card, attr)}
            if diff:
                changed += 1
                detail = "; ".join(f"{a}: {b} -> {n}" for a, (b, n) in diff.items())
                print(f"  {card.name!r}: {detail}")
        if apply:
            await session.commit()
            print(f"APPLIED：扫描 {len(cards)} 张，改动 {changed} 张。")
        else:
            await session.rollback()
            print(f"DRY-RUN：扫描 {len(cards)} 张，将改动 {changed} 张（加 --apply 写库）。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="写库（默认 dry-run）")
    asyncio.run(main(parser.parse_args().apply))
