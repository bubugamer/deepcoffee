"""记忆系统单元测试：注入层（L1/L2/L3）、画像抽取、会话摘要、记忆仓库。

模型路径一律用 FakeGateway 注入；记忆仓库走 conftest 配好的测试库。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.core.db import get_sessionmaker
from app.repositories.profiles import profile_repository
from app.repositories.user_memories import user_memory_repository
from app.services import memory_context, memory_extract, session_summary


# ---------- 注入层 memory_context ----------


def test_build_history_image_placeholder_and_order() -> None:
    turns = [
        {"role": "user", "content": "KALITA 怎么样"},
        {"role": "assistant", "content": "平底三孔…"},
        {"role": "user", "content": "看图", "images": ["http://x/a.jpg"]},
    ]
    msgs, text = memory_context.build_history(turns)
    assert msgs == [
        {"role": "user", "content": "KALITA 怎么样"},
        {"role": "assistant", "content": "平底三孔…"},
        {"role": "user", "content": "看图 [图片]"},
    ]
    assert text.startswith("用户：KALITA 怎么样")


def test_build_history_caps_and_skips() -> None:
    many = [{"role": "user", "content": f"m{i}"} for i in range(30)]
    msgs, _ = memory_context.build_history(many, max_turns=10)
    assert len(msgs) == 10 and msgs[0]["content"] == "m20"
    mixed = [{"role": "system", "content": "x"}, {"role": "user", "content": ""}, {"foo": 1}]
    assert memory_context.build_history(mixed) == ([], "")


def test_build_profile_text_groups_by_kind() -> None:
    mems = [
        {"kind": "taste", "content": "偏甜"},
        {"kind": "taste", "content": "怕酸"},
        {"kind": "equipment", "content": "V60"},
    ]
    pt = memory_context.build_profile_text(mems)
    assert "口味：偏甜；怕酸" in pt and "器具：V60" in pt
    assert memory_context.build_profile_text(None) == ""


def test_build_memory_context_injects_profile_and_summary() -> None:
    cs = SimpleNamespace(
        recent_messages=[{"role": "user", "content": "hi"}],
        summary=[{"topic": "耶加", "content": "花香不足", "time_hint": "6/12"}],
    )
    mc = memory_context.build_memory_context(cs, user_memories=[{"kind": "taste", "content": "怕酸"}])
    bg = mc.history_messages[0]
    assert bg["role"] == "system"
    assert "用户长期偏好与习惯" in bg["content"] and "更早对话摘要" in bg["content"]
    assert mc.history_messages[1] == {"role": "user", "content": "hi"}
    assert mc.history_text == "用户：hi"  # 背景不混进给调度器的对话文本
    assert "耶加：花香不足（6/12）" in mc.summary_text


def test_build_memory_context_no_memory_no_background() -> None:
    cs = SimpleNamespace(recent_messages=[{"role": "user", "content": "hi"}], summary=[])
    mc = memory_context.build_memory_context(cs)
    assert mc.history_messages == [{"role": "user", "content": "hi"}]
    assert mc.profile_text == "" and mc.summary_text == ""


# ---------- FakeGateway（仿 test_web_verify）----------


class _FakeGateway:
    def __init__(self, content: str, enabled: bool = True) -> None:
        self._content = content
        self.enabled = enabled
        self.vision_enabled = False

    async def chat(self, **kwargs):  # noqa: ANN003
        return SimpleNamespace(content=self._content)


# ---------- 画像抽取 memory_extract ----------


def test_extract_memories_parses_and_filters() -> None:
    content = (
        '{"memories":['
        '{"kind":"taste","content":"怕酸","confidence":0.9},'
        '{"kind":"bogus","content":"x","confidence":0.5},'
        '{"kind":"goal","content":"","confidence":0.5},'
        '{"kind":"habit","content":"细粉快冲","confidence":2}'
        "]}"
    )
    out = asyncio.run(
        memory_extract.extract_memories(recent_dialog="...", model="m", gateway=_FakeGateway(content))
    )
    assert {"kind": "taste", "content": "怕酸", "confidence": 0.9} in out
    # bogus kind / 空 content 被过滤；confidence=2 被 clamp 到 1.0
    assert {"kind": "habit", "content": "细粉快冲", "confidence": 1.0} in out
    assert len(out) == 2


def test_extract_memories_degrades() -> None:
    assert asyncio.run(
        memory_extract.extract_memories(model="m", gateway=_FakeGateway("x", enabled=False))
    ) == []
    assert asyncio.run(
        memory_extract.extract_memories(recent_dialog="a", model="m", gateway=_FakeGateway("not json"))
    ) == []


# ---------- 会话摘要 session_summary ----------


def test_update_summary_parses() -> None:
    content = '{"summary":[{"topic":"V60","content":"倾向干净","time_hint":"6/14"},{"topic":"","content":"skip"}]}'
    dropped = [{"role": "user", "content": "聊 V60"}]
    out = asyncio.run(
        session_summary.update_summary(
            existing_summary=[], dropped_turns=dropped, model="m", gateway=_FakeGateway(content)
        )
    )
    assert out == [{"topic": "V60", "content": "倾向干净", "time_hint": "6/14"}]


def test_update_summary_no_dropped_returns_none() -> None:
    assert (
        asyncio.run(
            session_summary.update_summary(
                existing_summary=[], dropped_turns=[], model="m", gateway=_FakeGateway("x")
            )
        )
        is None
    )


def test_update_summary_degrades() -> None:
    dropped = [{"role": "user", "content": "x"}]
    assert (
        asyncio.run(
            session_summary.update_summary(
                existing_summary=[], dropped_turns=dropped, model="m", gateway=_FakeGateway("bad", enabled=False)
            )
        )
        is None
    )
    assert (
        asyncio.run(
            session_summary.update_summary(
                existing_summary=[], dropped_turns=dropped, model="m", gateway=_FakeGateway("not json")
            )
        )
        is None
    )


# ---------- 记忆仓库 user_memories（真测试库）----------


def test_user_memory_upsert_dedupe_and_dismiss() -> None:
    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await profile_repository.get_or_create(session, "mem-user-1", "m1@x.com")
            r = user_memory_repository
            m1 = await r.upsert(session, user_id="mem-user-1", kind="taste", content="怕酸", confidence=0.6)
            # 同 kind + 归一化内容相同 → 更新而非新增，取较高 confidence
            m2 = await r.upsert(session, user_id="mem-user-1", kind="taste", content=" 怕酸 ", confidence=0.9)
            assert m1.id == m2.id and m2.confidence == 0.9
            assert len(await r.list_active(session, "mem-user-1")) == 1
            # dismiss 后同内容不复活、不新建
            await r.dismiss(session, user_id="mem-user-1", memory_id=m1.id)
            assert await r.list_active(session, "mem-user-1") == []
            m3 = await r.upsert(session, user_id="mem-user-1", kind="taste", content="怕酸", confidence=0.95)
            assert m3.id == m1.id and m3.status == "dismissed"
            assert await r.list_active(session, "mem-user-1") == []
            await session.rollback()

    asyncio.run(_run())
