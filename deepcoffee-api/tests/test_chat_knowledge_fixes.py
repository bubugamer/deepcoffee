"""小 PR 回归测试：#11 文章来源段去内部条目、#12 知识库回答 max_tokens、#13 direct_answer 真正生成回答。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.schemas.coffea import DispatchPlan
from app.schemas.knowledge import GroundingDoc
from app.services.ai_answer import answer_with_model
from app.services.coffea_executor import _INTENT_ONLY, assemble_reply, execute_plan
from app.services.knowledge_service import strip_internal_source_lines


# ---------- #11 文章「来源」段：去内部条目、留公开链接 ----------


def test_strip_internal_source_lines_drops_resources_keeps_public() -> None:
    md = (
        "## 来源\n\n"
        "- [SCA Coffee Standards](https://sca.coffee/)（official）\n"
        "- DeepCoffee existing grinder notes: `resources/107 磨豆机 [refined].md`\n"
        "- [Sucafina](https://www.sucafina.com/)\n"
    )
    out = strip_internal_source_lines(md)
    assert "## 来源" in out  # 来源段标题保留
    assert "https://sca.coffee/" in out  # 公开链接保留
    assert "https://www.sucafina.com/" in out
    assert "resources/107" not in out  # 指向 resources/ 的内部条目被删


def test_strip_internal_source_lines_only_inside_sources_section() -> None:
    md = (
        "## 正文\n\n"
        "- 这里引用 resources/foo.md，不在来源段，不应被删\n\n"
        "## 来源\n\n"
        "- `resources/bar.md`\n"
    )
    out = strip_internal_source_lines(md)
    assert "resources/foo.md" in out  # 非来源段的 resources/ 不动
    assert "resources/bar.md" not in out  # 来源段内的删除


# ---------- #12 知识库回答 max_tokens 足够大，不再截断 ----------


def test_knowledge_answer_uses_large_max_tokens() -> None:
    captured: dict = {}

    class _G:
        enabled = True
        vision_enabled = False

        async def chat(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)
            return SimpleNamespace(content="答案", model="fake")

    asyncio.run(
        answer_with_model(
            "问题", [GroundingDoc(slug="s", title="t", content="c")], model="m", gateway=_G()
        )
    )
    assert captured.get("max_tokens", 0) >= 3000


# ---------- #13 direct_answer 真正生成回答（不再空回复） ----------


class _FakeCoachGateway:
    enabled = True
    vision_enabled = False

    async def chat(self, **kwargs):  # noqa: ANN003
        return SimpleNamespace(content="冲出来很酸通常是萃取不足，可以先调细一点试试。", model="fake")


_SETTINGS = SimpleNamespace(vision_model=None)


def test_direct_answer_not_intent_only() -> None:
    # direct_answer 不再属「纯意图、不执行」——否则回答全靠 direct_reply、常为空。
    assert "direct_answer" not in _INTENT_ONLY


def test_direct_answer_generates_real_reply() -> None:
    # 调度器只给意图、没给 action 时，也要补一个 direct_answer 动作并真正生成回答。
    plan = DispatchPlan(primary_intent="direct_answer", actions=[])
    results = asyncio.run(
        execute_plan(
            plan,
            message="冲出来很酸是细粉多吗？还需要调细？",
            attachments=None,
            session_state={},
            knowledge_service=None,
            settings=_SETTINGS,
            model="m",
            gateway=_FakeCoachGateway(),
        )
    )
    answer = next((r for r in results if r.type == "direct_answer"), None)
    assert answer is not None and answer.message
    reply = assemble_reply(plan, results)
    assert reply and "萃取" in reply
