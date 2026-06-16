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


# ---------- 阶段 2：疑似提示 + 并入 ----------


def test_find_similar_includes_abbreviation_substring() -> None:
    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="SEY Coffee"
            )
            sims = await entity_repository.find_similar(session, "roaster", "SEY")
            assert any(e.canonical_name == "SEY Coffee" for e in sims)  # 缩写子串 → 疑似提示
            await session.rollback()

    asyncio.run(_run())


def test_merge_candidate_into_entity_registers_alias() -> None:
    from app.repositories.candidates import candidate_repository
    from app.repositories.profiles import profile_repository
    from app.services.candidate_service import candidate_service

    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await profile_repository.get_or_create(session, "admin-merge", "a@x.com")
            ent = await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="SEY Coffee"
            )
            cand = await candidate_repository.create(
                session,
                entity_type="roaster",
                title="SEY",
                payload={"name": "SEY"},
                source_table=None,
                source_record_id=None,
                source_user_id=None,
            )
            merged = await candidate_service.merge_candidate_into_entity(
                session, cand.id, entity_id=ent.id, reviewer_id="admin-merge"
            )
            assert merged is not None
            assert merged.status == "merged" and merged.proposed_entity_id == ent.id
            # 并入后 "SEY" 能解析到该实体（别名已登记），不再会建新实体
            r = await entity_repository.resolve_entity(session, "roaster", "SEY")
            assert r is not None and r.id == ent.id
            await session.rollback()

    asyncio.run(_run())


# ---------- 阶段 3：豆卡关联实体 + 搜索聚合 ----------


def test_bean_links_roaster_and_search_aggregates() -> None:
    from app.repositories.beans import bean_repository
    from app.repositories.profiles import profile_repository
    from app.schemas.bean import BeanDraft

    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await profile_repository.get_or_create(session, "u-bean", "u@x.com")
            await entity_repository.upsert(session, entity_type="roaster", canonical_name="Coffee Buff")
            id1 = await bean_repository.create(
                session,
                user_id="u-bean",
                draft=BeanDraft(name="豆A", roaster_name="coffee buff"),
                source_type="text",
                raw_input=None,
                trace_id="t1",
            )
            id2 = await bean_repository.create(
                session,
                user_id="u-bean",
                draft=BeanDraft(name="豆B", roaster_name="Coffeebuff"),
                source_type="text",
                raw_input=None,
                trace_id="t2",
            )
            b1 = await bean_repository.get(session, user_id="u-bean", bean_id=id1)
            b2 = await bean_repository.get(session, user_id="u-bean", bean_id=id2)
            # 两种写法都回填到同一烘焙商实体，规范名统一
            assert b1.roaster_entity_id is not None
            assert b1.roaster_entity_id == b2.roaster_entity_id
            assert b1.roaster_canonical == "Coffee Buff"
            # 搜其中一种写法 → 聚合搜出两张
            beans, _ = await bean_repository.list(session, user_id="u-bean", q="coffeebuff")
            assert {"豆A", "豆B"} <= {b.name for b in beans}
            await session.rollback()

    asyncio.run(_run())


# ---------- 阶段 4：合并 / 规范主名 / 扫描重复 ----------


def test_merge_entities_migrates_refs_and_alias() -> None:
    from app.models.tables import PublicEntity as PE
    from app.repositories.beans import bean_repository
    from app.repositories.profiles import profile_repository
    from app.schemas.bean import BeanDraft

    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await profile_repository.get_or_create(session, "u-merge", "m@x.com")
            target = await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="SEY Coffee"
            )
            source = await entity_repository.upsert(session, entity_type="roaster", canonical_name="SEY")
            bid = await bean_repository.create(
                session,
                user_id="u-merge",
                draft=BeanDraft(name="豆", roaster_name="SEY"),
                source_type="text",
                raw_input=None,
                trace_id="t",
            )
            b = await bean_repository.get(session, user_id="u-merge", bean_id=bid)
            assert b.roaster_entity_id == source.id  # 合并前关联到 source
            merged = await entity_repository.merge_entities(
                session, source_id=source.id, target_id=target.id
            )
            assert merged is not None and merged.id == target.id
            # source 标记 merged；"SEY" 改为解析到 target；豆卡引用迁到 target
            src = await session.get(PE, source.id)
            assert src.status == "merged"
            r = await entity_repository.resolve_entity(session, "roaster", "SEY")
            assert r is not None and r.id == target.id
            b2 = await bean_repository.get(session, user_id="u-merge", bean_id=bid)
            assert b2.roaster_entity_id == target.id
            await session.rollback()

    asyncio.run(_run())


def test_rename_canonical_keeps_old_name_searchable() -> None:
    async def _run() -> None:
        async with get_sessionmaker()() as session:
            ent = await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="Captain George / 乔治队长"
            )
            renamed = await entity_repository.rename_canonical(
                session, entity_id=ent.id, new_canonical="乔治队长"
            )
            assert renamed is not None and renamed.canonical_name == "乔治队长"
            # 旧的英文名 / 混合名仍能解析到同一实体（旧名转成了别名）
            r1 = await entity_repository.resolve_entity(session, "roaster", "Captain George")
            r2 = await entity_repository.resolve_entity(session, "roaster", "Captain George / 乔治队长")
            assert r1 is not None and r1.id == ent.id
            assert r2 is not None and r2.id == ent.id
            await session.rollback()

    asyncio.run(_run())


def test_find_duplicate_groups_detects_form_dupes() -> None:
    from app.models.tables import PublicEntity as PE
    from app.repositories.entities import normalize_name

    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await entity_repository.upsert(session, entity_type="roaster", canonical_name="Coffee Buff")
            # 直接造一个形态重复实体（绕过 upsert 判重，模拟阶段 1 前的历史遗留）
            session.add(
                PE(
                    id="ent_dupe_cb",
                    entity_type="roaster",
                    canonical_name="Coffeebuff",
                    normalized_name=normalize_name("Coffeebuff"),
                    scope="public",
                    status="active",
                    created_from="seed",
                )
            )
            await session.flush()
            groups = await entity_repository.find_duplicate_groups(session, entity_type="roaster")
            assert any(
                {e.canonical_name for e in members} >= {"Coffee Buff", "Coffeebuff"}
                for _reason, members in groups
            )
            await session.rollback()

    asyncio.run(_run())
