from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from pathlib import Path

from app.models.tables import (
    EntityAlias,
    EntitySource,
    PublicEntity,
    Roaster,
    RoasterProduct,
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


def test_resync_skips_alias_already_present_from_other_source() -> None:
    """frontmatter 别名已以其它来源（如 auto 回填）存在时，重导应跳过、不撞唯一约束。"""
    async def _run() -> None:
        from sqlalchemy import delete as sqldelete, update as sqlupdate
        from app.models.tables import KnowledgeSyncRecord

        sm = get_sessionmaker()
        async with sm() as session:
            imp = _importer()
            await imp.run(session, dry_run=False)
            await session.flush()
            # 取一个有 frontmatter 别名的实体（哥斯达黎加 origin，别名 Costa Rica）
            ent = (
                await session.execute(
                    select(PublicEntity).where(PublicEntity.normalized_name == normalize_name("哥斯达黎加"))
                )
            ).scalar_one()
            key = normalize_name("Costa Rica")
            # 把这条 markdown_seed 别名改成 auto 来源，并删掉台账逼重导走「按名匹配 → update」
            await session.execute(
                sqlupdate(EntityAlias)
                .where(EntityAlias.entity_id == ent.id, EntityAlias.normalized_alias == key)
                .values(source="auto")
            )
            await session.execute(
                sqldelete(KnowledgeSyncRecord).where(KnowledgeSyncRecord.entity_id == ent.id)
            )
            await session.flush()
            # 重导：修复前这里会因 (entity_id, normalized_alias) 唯一约束 IntegrityError
            await imp.run(session, dry_run=False)
            await session.flush()
            cnt = (
                await session.execute(
                    select(func.count())
                    .select_from(EntityAlias)
                    .where(EntityAlias.entity_id == ent.id, EntityAlias.normalized_alias == key)
                )
            ).scalar_one()
            assert cnt == 1
            await session.rollback()

    asyncio.run(_run())


def test_same_batch_links_roaster_product_to_roaster() -> None:
    async def _run() -> None:
        sm = get_sessionmaker()
        async with sm() as session:
            await _importer().run(session, dry_run=False)
            await session.commit()

            roaster = (
                await session.execute(
                    select(PublicEntity).where(
                        PublicEntity.entity_type == "roaster",
                        PublicEntity.normalized_name == normalize_name("DAK Coffee Roasters"),
                    )
                )
            ).scalar_one()
            # DAK Milky Cake 是具体单品（非产品线），应正常建实体并连上烘焙商。
            product = (
                await session.execute(
                    select(PublicEntity).where(
                        PublicEntity.normalized_name == normalize_name("DAK Milky Cake")
                    )
                )
            ).scalar_one()
            row = await session.get(RoasterProduct, product.id)
            assert row.roaster_name == "DAK Coffee Roasters"
            assert row.roaster_entity_id == roaster.id  # 同批精确名匹配连上了外键


def test_product_line_seeds_are_skipped() -> None:
    """产品线/项目类产品种子（product_type 含 line/program/... ）不建实体；具体单品照常建。"""
    imp = _importer()
    rel = Path("roaster-products/x.md")

    def build(etype: str, product_type: str):
        meta = {
            "title": f"Demo {product_type}",
            "entity_type": etype,
            "product_type": product_type,
            "visibility": "support",
            "knowledge_role": "entity_seed",
        }
        return imp._build_seed(rel, meta, body="# Demo\n\n正文。", raw="raw")

    # 产品线/项目/订阅/系列/选品/平台 → 跳过（返回 None）
    for pt in ("product_line", "green_coffee_program", "selection_program", "subscription", "filter_series", "small_bag_green_coffee_platform"):
        assert build("roaster_product", pt) is None, pt
        assert build("green_bean_product", pt) is None, pt
    # 具体单品 → 照常建（非 None）
    assert build("roaster_product", "blend") is not None
    assert build("green_bean_product", "microlot") is not None
    # 守卫只作用于产品类;其它类型不受影响
    other = imp._build_seed(
        Path("varietals/x.md"),
        {"title": "Demo V", "entity_type": "varietal", "product_type": "anything_line", "visibility": "support", "knowledge_role": "entity_seed"},
        body="# Demo\n\n正文。", raw="raw",
    )
    assert other is not None


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
