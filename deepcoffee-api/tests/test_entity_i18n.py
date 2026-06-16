"""实体名多语言（阶段 1+2）：detect_locale 语言判定 + 别名打 locale + 按语言取 display_name。"""

from __future__ import annotations

import asyncio

from app.repositories.entities import alias_fragments, detect_locale, entity_repository


# ---------- 纯函数：语言判定 ----------


def test_alias_fragments_splits_parenthetical_bilingual() -> None:
    # 「中文（English）」括号双语名拆成中、英两半，整名保留
    f = alias_fragments("哥斯达黎加（Costa Rica）")
    assert "哥斯达黎加" in f and "Costa Rica" in f
    assert "哥斯达黎加（Costa Rica）" in f
    # 英文（中文）方向同样拆
    f2 = alias_fragments("Finca Santo Niño（圣尼佐庄园）")
    assert "Finca Santo Niño" in f2 and "圣尼佐庄园" in f2


def test_alias_fragments_keeps_parenthetical_note_intact() -> None:
    # 括号里是注释（判不出干净语言）→ 不拆，避免误把注释当成别名
    f = alias_fragments("1zpresso ZP6（含 ZP6S 特调版）")
    assert f == ["1zpresso ZP6（含 ZP6S 特调版）"]


def test_detect_locale_basic_scripts() -> None:
    assert detect_locale("乔治队长") == "zh"
    assert detect_locale("Captain George") == "en"
    assert detect_locale("Café Onyx") == "en"  # 西欧重音仍算拉丁
    assert detect_locale("カーボニックマセレーション") == "ja"  # 片假名
    assert detect_locale("ほうじ茶") == "ja"  # 假名 + 汉字 → ja


def test_detect_locale_mixed_and_empty_are_none() -> None:
    # 中英混写不算任一语言的显示名，只继续参与匹配
    assert detect_locale("二氧化碳浸渍 / Carbonic Maceration") is None
    assert detect_locale("") is None
    assert detect_locale("   ") is None
    assert detect_locale("123 / 456") is None  # 纯符号数字


def test_detect_locale_fullwidth_latin_normalizes_to_en() -> None:
    assert detect_locale("ＳＥＹ") == "en"  # 全角拉丁经 NFKC → 半角 → en


# ---------- 走测试库：别名打 locale + 按语言取显示名 ----------


def test_localized_names_split_from_mixed_name() -> None:
    async def _run() -> None:
        async with entity_repository_session() as session:
            ent = await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="Captain George / 乔治队长"
            )
            names = await entity_repository.localized_names_for(session, [ent.id])
            per = names.get(ent.id, {})
            # 中英片段各自打标，混合整名不作显示名（locale=None 不入表选取）
            assert per.get("en") == "Captain George"
            assert per.get("zh") == "乔治队长"
            await session.rollback()

    asyncio.run(_run())


def test_attach_localized_picks_by_locale_with_fallback() -> None:
    async def _run() -> None:
        async with entity_repository_session() as session:
            await entity_repository.upsert(
                session, entity_type="roaster", canonical_name="Captain George / 乔治队长"
            )
            # 英文界面
            items_en = await entity_repository.list(session, entity_type="roaster", locale="en")
            cap_en = next(e for e in items_en if e.canonical_name == "Captain George / 乔治队长")
            assert cap_en.display_name == "Captain George"
            assert cap_en.localized_names.get("zh") == "乔治队长"
            # 中文界面
            items_zh = await entity_repository.list(session, entity_type="roaster", locale="zh")
            cap_zh = next(e for e in items_zh if e.canonical_name == "Captain George / 乔治队长")
            assert cap_zh.display_name == "乔治队长"
            # 没录过的语言 → 回退主名
            items_ja = await entity_repository.list(session, entity_type="roaster", locale="ja")
            cap_ja = next(e for e in items_ja if e.canonical_name == "Captain George / 乔治队长")
            assert cap_ja.display_name == "Captain George / 乔治队长"
            # 不传 locale → 回退主名
            items_none = await entity_repository.list(session, entity_type="roaster")
            cap_none = next(e for e in items_none if e.canonical_name == "Captain George / 乔治队长")
            assert cap_none.display_name == "Captain George / 乔治队长"
            await session.rollback()

    asyncio.run(_run())


def entity_repository_session():
    from app.core.db import get_sessionmaker

    return get_sessionmaker()()
