from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models.tables import (
    EntityAlias,
    EntitySource,
    GreenBeanProduct,
    PublicEntity,
    Roaster,
)
from app.repositories.entities import normalize_name
from app.services.entity_seed_importer import EntitySeedImporter


def _importer() -> EntitySeedImporter:
    return EntitySeedImporter(get_settings().resolved_knowledge_dir)


async def _count(session, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


def test_dry_run_plans_creates_but_writes_nothing() -> None:
    async def _run() -> None:
        sm = get_sessionmaker()
        async with sm() as session:
            report = await _importer().run(session, dry_run=True)
            # 应规划出一大批实体（库里约 130 个 entity_seed 页），且覆盖多种类型。
            assert len(report.created) > 100
            assert {"roaster", "coffee_source", "green_bean_merchant"} <= set(report.by_type)
            # dry-run 一个字都没写。
            assert await _count(session, PublicEntity) == 0

    asyncio.run(_run())


def test_apply_writes_entity_typed_alias_source() -> None:
    async def _run() -> None:
        sm = get_sessionmaker()
        async with sm() as session:
            report = await _importer().run(session, dry_run=False)
            await session.commit()
            assert await _count(session, PublicEntity) == len(report.created)

            aokka = (
                await session.execute(
                    select(PublicEntity).where(PublicEntity.normalized_name == normalize_name("AOKKA Coffee"))
                )
            ).scalar_one()
            assert aokka.entity_type == "roaster"
            assert aokka.created_from == "markdown"
            assert aokka.status == "needs_verification"  # 按 frontmatter 透传，未被强行 active

            roaster = await session.get(Roaster, aokka.id)
            assert roaster.market == "domestic"
            assert roaster.roaster_subtype == "roastery_brand"

            aliases = (
                await session.execute(select(EntityAlias).where(EntityAlias.entity_id == aokka.id))
            ).scalars().all()
            assert any("AOKKA" in a.alias for a in aliases)
            sources = (
                await session.execute(select(EntitySource).where(EntitySource.entity_id == aokka.id))
            ).scalars().all()
            assert sources and all(s.source_type for s in sources)

    asyncio.run(_run())


def test_resync_is_idempotent() -> None:
    async def _run() -> None:
        sm = get_sessionmaker()
        async with sm() as session:
            await _importer().run(session, dry_run=False)
            await session.commit()
            first = await _count(session, PublicEntity)
            report2 = await _importer().run(session, dry_run=False)
            await session.commit()
            # 内容没变：第二遍零新建、零更新，全部跳过；总数不变。
            assert report2.created == []
            assert report2.updated == []
            assert len(report2.skipped) > 100
            assert await _count(session, PublicEntity) == first

    asyncio.run(_run())


def test_same_batch_links_product_to_merchant() -> None:
    async def _run() -> None:
        sm = get_sessionmaker()
        async with sm() as session:
            await _importer().run(session, dry_run=False)
            await session.commit()

            merchant = (
                await session.execute(
                    select(PublicEntity).where(
                        PublicEntity.entity_type == "green_bean_merchant",
                        PublicEntity.normalized_name == normalize_name("Ally Coffee"),
                    )
                )
            ).scalar_one()
            product = (
                await session.execute(
                    select(PublicEntity).where(
                        PublicEntity.normalized_name == normalize_name("Ally Coffee Core Coffee Program")
                    )
                )
            ).scalar_one()
            row = await session.get(GreenBeanProduct, product.id)
            assert row.merchant_name == "Ally Coffee"
            assert row.merchant_entity_id == merchant.id  # 同批精确名匹配连上了外键

    asyncio.run(_run())


def test_ownership_human_touched_is_read_only() -> None:
    async def _run() -> None:
        sm = get_sessionmaker()
        async with sm() as session:
            await _importer().run(session, dry_run=False)
            await session.commit()

            aokka = (
                await session.execute(
                    select(PublicEntity).where(PublicEntity.normalized_name == normalize_name("AOKKA Coffee"))
                )
            ).scalar_one()
            # 模拟被提案/人工接管。
            aokka.created_from = "proposal"
            aokka.summary = "人工编辑过的简述"
            await session.commit()

            report = await _importer().run(session, dry_run=False)
            await session.commit()
            # 这条应被跳过（只读），且人工内容未被覆盖。
            assert any("AOKKA" in name and "只读" in reason for _, name, reason in report.skipped)
            refreshed = await session.get(PublicEntity, aokka.id)
            assert refreshed.created_from == "proposal"
            assert refreshed.summary == "人工编辑过的简述"

    asyncio.run(_run())
