"""实体消歧阶段 1：disambig_key / alias_fragments / resolve_entity / 自动建别名 / 判重复用。"""

from __future__ import annotations

import asyncio

from app.core.db import get_sessionmaker
from app.repositories.entities import (
    alias_fragments,
    disambig_key,
    entity_repository,
)


# ---------- 纯函数 ----------


def test_disambig_key_collapses_form_differences() -> None:
    assert disambig_key("Coffee Buff") == "coffeebuff"
    assert disambig_key("coffee buff") == "coffeebuff"
    assert disambig_key("Coffeebuff") == "coffeebuff"
    assert disambig_key("ＳＥＹ") == "sey"  # 全角 → 半角


def test_alias_fragments_splits_mixed_name() -> None:
    f = alias_fragments("Captain George / 乔治队长")
    assert "Captain George" in f and "乔治队长" in f
    assert "Captain George / 乔治队长" in f  # 整名也保留


# ---------- 走测试库：自动建别名 + 匹配 + 判重 ----------


def test_resolve_by_alias_and_disambig() -> None:
    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="Captain George / 乔治队长"
            )
            await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="Coffee Buff"
            )
            await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="SEY Coffee"
            )

            # 中英拆分别名命中
            assert await entity_repository.resolve_entity(session, "roaster", "乔治队长") is not None
            assert await entity_repository.resolve_entity(session, "roaster", "Captain George") is not None
            # 形态差异（去空格/大小写）自动命中
            r = await entity_repository.resolve_entity(session, "roaster", "Coffeebuff")
            assert r is not None and r.canonical_name == "Coffee Buff"
            # 缩写不自动命中（SEY ↛ SEY Coffee，交人工审核）
            assert await entity_repository.resolve_entity(session, "roaster", "SEY") is None
            # 类型隔离：同名不同类型不串
            assert await entity_repository.resolve_entity(session, "origin", "乔治队长") is None
            await session.rollback()

    asyncio.run(_run())


def test_upsert_idempotent_via_alias() -> None:
    async def _run() -> None:
        async with get_sessionmaker()() as session:
            e1 = await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="Captain George / 乔治队长"
            )
            # 再用别名"乔治队长"建 → 命中既有、不新建
            e2 = await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="乔治队长"
            )
            assert e1.id == e2.id
            # 形态差异也复用
            e3 = await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="coffee buff"
            )
            e4 = await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="Coffeebuff"
            )
            assert e3.id == e4.id
            await session.rollback()

    asyncio.run(_run())


def test_exists_active_is_alias_aware() -> None:
    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="Captain George / 乔治队长"
            )
            assert await entity_repository.exists_active(session, "roaster", "乔治队长") is True
            assert await entity_repository.exists_active(session, "roaster", "不存在的烘焙商") is False
            await session.rollback()

    asyncio.run(_run())
