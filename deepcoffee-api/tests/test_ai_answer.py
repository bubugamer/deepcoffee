from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.schemas.knowledge import GroundingDoc
from app.services.ai_answer import answer_with_model

_GROUNDING = [GroundingDoc(slug="geisha", title="瑰夏", content="瑰夏以茉莉花香、桃子、芒果风味著称…")]
_IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="


class _FakeGateway:
    enabled = True
    vision_enabled = True

    def __init__(self, content: str) -> None:
        self.content = content
        self.last_kwargs: dict = {}

    async def chat(self, **kwargs):  # noqa: ANN003
        self.last_kwargs = kwargs
        return SimpleNamespace(content=self.content, model="fake")


def _disabled_gateway() -> SimpleNamespace:
    return SimpleNamespace(enabled=False)


def test_answer_with_model_returns_none_when_gateway_disabled() -> None:
    result = asyncio.run(
        answer_with_model("瑰夏为什么有花香", _GROUNDING, model="deepseek-chat",
                          gateway=_disabled_gateway())
    )
    assert result is None


def test_answer_with_model_returns_none_without_grounding() -> None:
    enabled = SimpleNamespace(enabled=True)
    result = asyncio.run(
        answer_with_model("无来源问题", [], model="deepseek-chat", gateway=enabled)
    )
    assert result is None


def test_answer_with_model_uses_image_even_without_grounding() -> None:
    gw = _FakeGateway("这款水可以作为冲煮参考，但还要看矿物质含量。")
    result = asyncio.run(
        answer_with_model(
            "这个水冲咖啡合适吗",
            [],
            model="deepseek-chat",
            image_urls=[_IMG],
            vision_model="kimi-k2.6",
            gateway=gw,
        )
    )
    assert result == "这款水可以作为冲煮参考，但还要看矿物质含量。"
    assert gw.last_kwargs["model"] == "kimi-k2.6"
    user_msg = gw.last_kwargs["messages"][-1]
    assert isinstance(user_msg["content"], list)
    assert any(p.get("type") == "image_url" and p["image_url"]["url"] == _IMG for p in user_msg["content"])


def test_answer_with_model_sends_images_to_vision_model() -> None:
    gw = _FakeGateway("结合图片和知识库回答。")
    result = asyncio.run(
        answer_with_model(
            "这张图里的处理法是什么意思？",
            _GROUNDING,
            model="deepseek-chat",
            image_urls=[_IMG],
            vision_model="kimi-k2.6",
            gateway=gw,
        )
    )
    assert result == "结合图片和知识库回答。"
    assert gw.last_kwargs["model"] == "kimi-k2.6"
    user_msg = gw.last_kwargs["messages"][-1]
    assert isinstance(user_msg["content"], list)
    assert any(p.get("type") == "image_url" and p["image_url"]["url"] == _IMG for p in user_msg["content"])


def test_answer_with_model_includes_model_notes_as_hidden_context() -> None:
    gw = _FakeGateway("不要直接等同 Geisha。")
    result = asyncio.run(
        answer_with_model(
            "SL9 和 Geisha 一样吗？",
            [
                GroundingDoc(
                    slug="varietals__sl9",
                    title="SL9",
                    content="SL9 是少见品系。",
                    model_notes=["Gesha Inca 不能自动归并为 Geisha。"],
                )
            ],
            model="deepseek-chat",
            gateway=gw,
        )
    )
    assert result == "不要直接等同 Geisha。"
    user_text = gw.last_kwargs["messages"][-1]["content"]
    assert "Gesha Inca 不能自动归并为 Geisha" in user_text
    assert "不要把它们列为来源" in user_text


class _QuotaExhaustedGateway:
    enabled = True
    vision_enabled = False

    async def chat(self, **kwargs):  # noqa: ANN003
        raise RuntimeError('model provider call failed: {"error":{"message":"Insufficient Balance"}}')


class _CrashGateway:
    enabled = True
    vision_enabled = False

    async def chat(self, **kwargs):  # noqa: ANN003
        raise RuntimeError("connection reset by peer")


def test_answer_collects_provider_quota_reason() -> None:
    reasons: list[str] = []
    result = asyncio.run(
        answer_with_model(
            "瑰夏有什么风味？", _GROUNDING, model="m",
            gateway=_QuotaExhaustedGateway(), failure_reasons=reasons,
        )
    )
    assert result is None
    assert reasons == ["provider_quota"]


def test_answer_ordinary_failure_collects_nothing() -> None:
    reasons: list[str] = []
    result = asyncio.run(
        answer_with_model(
            "瑰夏有什么风味？", _GROUNDING, model="m",
            gateway=_CrashGateway(), failure_reasons=reasons,
        )
    )
    assert result is None
    assert reasons == []
