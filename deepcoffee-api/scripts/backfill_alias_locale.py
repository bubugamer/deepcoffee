"""一次性回填：给现有 entity_aliases 补 locale 语言标记（幂等，dry-run 默认）。

阶段 1 多语言上线后跑一次，让**已存在**的别名（此前 locale 全为 NULL）也带上 zh/ja/en，
这样阶段 2 的「按语言取显示名」对历史实体也生效。只填判得出语言的别名，混合名 / 形态变体
（detect_locale 返回 None）保持 NULL，仍只参与匹配。

用法（读 .env 的 DATABASE_URL）：
    cd deepcoffee-api && python -m scripts.backfill_alias_locale          # dry-run，只看分布
    cd deepcoffee-api && python -m scripts.backfill_alias_locale --apply  # 真正写库
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.models.tables import EntityAlias
from app.repositories.entities import detect_locale


async def main(apply: bool) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = await session.execute(select(EntityAlias).where(EntityAlias.locale.is_(None)))
        aliases = list(rows.scalars().all())
        changes: Counter[str] = Counter()
        for a in aliases:
            loc = detect_locale(a.alias)
            if loc is None:
                changes["(无法判定，保持 NULL)"] += 1
                continue
            changes[loc] += 1
            if apply:
                a.locale = loc
        if apply:
            await session.commit()

    mode = "已写库" if apply else "dry-run（未写库）"
    print(f"[{mode}] 待补 locale 的别名共 {len(aliases)} 条，判定分布：")
    for loc, n in sorted(changes.items()):
        print(f"  {loc}: {n}")
    if not apply:
        print("加 --apply 真正写入。")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
