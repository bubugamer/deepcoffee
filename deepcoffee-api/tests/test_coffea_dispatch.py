from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.services import coffea_dispatch
from app.services.coffea_dispatch import dispatch, dispatch_with_model, local_dispatch


class _FakeGateway:
    """enabled=True 的假网关，chat 返回预置内容。"""

    enabled = True

    def __init__(self, content: str) -> None:
        self.content = content
        self.last_kwargs: dict = {}

    async def chat(self, **kwargs):  # noqa: ANN003
        self.last_kwargs = kwargs
        return SimpleNamespace(content=self.content, model="fake")


_VALID_PLAN = json.dumps(
    {
        "primary_intent": "read_bean_card_image",
        "secondary_intents": ["recommend_brew_params"],
        "actions": [{"type": "read_bean_card_image", "input_ref": "attachment_1"}],
        "state_updates": {},
        "direct_reply": None,
        "should_answer_directly": False,
    }
)


# --- 模型路径 --------------------------------------------------------------

def test_model_path_parses_plan() -> None:
    plan = asyncio.run(
        dispatch(message="读下这张豆卡", model="m", gateway=_FakeGateway(_VALID_PLAN))
    )
    assert plan.source == "model"
    assert plan.primary_intent == "read_bean_card_image"
    assert plan.secondary_intents == ["recommend_brew_params"]
    assert plan.actions[0]["type"] == "read_bean_card_image"


def test_model_path_drops_unexpected_keys() -> None:
    payload = json.dumps({"primary_intent": "direct_answer", "direct_reply": "你好，我是 Coffea。", "evil_key": "x"})
    plan = asyncio.run(
        dispatch_with_model(message="hi", model="m", gateway=_FakeGateway(payload))
    )
    assert plan is not None
    assert plan.primary_intent == "direct_answer"
    assert plan.direct_reply == "你好，我是 Coffea。"


def test_model_unknown_intent_falls_back_local() -> None:
    # 非白名单意图 → 模型路径 None → 回退本地（消息含知识问号 → knowledge_answer）。
    gw = _FakeGateway(json.dumps({"primary_intent": "definitely_not_allowed"}))
    plan = asyncio.run(dispatch(message="瑰夏为什么有花香？", model="m", gateway=gw))
    assert plan.source == "local"
    assert plan.primary_intent == "knowledge_answer"


def test_model_invalid_json_falls_back_local() -> None:
    plan = asyncio.run(
        dispatch(message="网上对这支豆评价怎么样", model="m", gateway=_FakeGateway("not json"))
    )
    assert plan.source == "local"
    assert plan.primary_intent == "web_verify"


def test_disabled_gateway_returns_none() -> None:
    disabled = SimpleNamespace(enabled=False)
    result = asyncio.run(
        dispatch_with_model(message="hi", model="m", gateway=disabled)
    )
    assert result is None


# --- 本地兜底分支 ----------------------------------------------------------

def test_local_image_without_clear_text_asks_clarification() -> None:
    plan = local_dispatch(message="看看这个", attachments=[{"type": "image"}])
    assert plan.primary_intent == "ask_clarification"
    assert plan.direct_reply


def test_local_image_reads_bean_card_when_text_says_bean_card() -> None:
    plan = local_dispatch(message="帮我看看这张豆卡", attachments=[{"type": "image"}])
    assert plan.primary_intent == "read_bean_card_image"
    assert plan.source == "local"


def test_local_image_brew_photo() -> None:
    plan = local_dispatch(message="冲完了，看下粉床", attachments=[{"type": "image"}])
    assert plan.primary_intent == "adjust_brew_params"
    assert plan.actions[0]["type"] == "adjust_brew_params"


def test_local_web_verify() -> None:
    plan = local_dispatch(message="网上说这支豆有设计缺陷，是真的吗")
    assert plan.primary_intent == "web_verify"


def test_local_recommend_needs_active_bean() -> None:
    with_bean = local_dispatch(message="给我一个冲煮方案", session_state={"active_bean_id": "b1"})
    assert with_bean.primary_intent == "recommend_brew_params"
    # 没有 active 豆时不该直接推参数。
    without_bean = local_dispatch(message="给我一个冲煮方案")
    assert without_bean.primary_intent != "recommend_brew_params"


def test_local_knowledge() -> None:
    plan = local_dispatch(message="什么是厌氧处理")
    assert plan.primary_intent == "knowledge_answer"


def test_local_ask_clarification_default() -> None:
    plan = local_dispatch(message="嗯")
    assert plan.primary_intent == "ask_clarification"
    assert plan.direct_reply


def test_allowed_intents_match_doc_count() -> None:
    # 与 §1 提示词「允许的 primary_intent / action.type」对齐（15 项）。
    assert len(coffea_dispatch.ALLOWED_INTENTS) == 15
    assert coffea_dispatch.INTENT_ONLY <= set(coffea_dispatch.ALLOWED_INTENTS)


# --- 附件元信息：调度提示词绝不携带 base64 原文 -----------------------------

def test_dispatch_prompt_excludes_attachment_base64() -> None:
    """回归：base64 不应进入调度提示词。提示词里只能有附件元信息。"""
    gw = _FakeGateway(_VALID_PLAN)
    big_data_url = "data:image/jpeg;base64," + "A" * 200_000
    asyncio.run(
        dispatch_with_model(
            message="好的，请帮我记录这只豆子",
            attachments=[{"type": "image", "data_url": big_data_url, "mime_type": "image/jpeg"}],
            model="m",
            gateway=gw,
        )
    )
    user_content = gw.last_kwargs["messages"][1]["content"]
    assert "base64,AAAA" not in user_content
    assert len(user_content) < 10_000
    assert "attachment_1" in user_content  # 元信息仍在，模型知道有一张图


def test_local_image_with_record_bean_text_reads_card() -> None:
    """带图说「记录这只豆子」应直接走读卡建档，而不是反问。"""
    plan = local_dispatch(message="好的，请帮我记录这只豆子", attachments=[{"type": "image"}])
    assert plan.primary_intent == "read_bean_card_image"


class _CrashGateway:
    """chat 抛普通网络错误的假网关。"""

    enabled = True

    async def chat(self, **kwargs):  # noqa: ANN003
        raise RuntimeError("connection reset by peer")


def test_dispatch_falls_back_on_model_failure() -> None:
    plan = asyncio.run(dispatch(message="随便聊聊", model="m", gateway=_CrashGateway()))
    assert plan.source == "local"
    assert plan.degrade_reason is None


class _QuotaExhaustedGateway:
    """chat 抛厂商配额/欠费错误的假网关（如 DeepSeek 402 Insufficient Balance）。"""

    enabled = True

    async def chat(self, **kwargs):  # noqa: ANN003
        raise RuntimeError('model provider call failed: {"error":{"message":"Insufficient Balance"}}')


def test_dispatch_tags_provider_quota_on_exhausted_key() -> None:
    plan = asyncio.run(dispatch(message="随便聊聊", model="m", gateway=_QuotaExhaustedGateway()))
    assert plan.source == "local"
    assert plan.degrade_reason == "provider_quota"
