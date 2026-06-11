from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.brew_coach import coach_with_model

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


def test_coach_none_when_gateway_disabled() -> None:
    out = asyncio.run(
        coach_with_model(message="x", model="m", gateway=SimpleNamespace(enabled=False))
    )
    assert out is None


def test_coach_returns_free_text() -> None:
    gw = _FakeGateway("先保持 1:15 粉水比，把 22g 等比缩到 15g：水量约 225ml。")
    out = asyncio.run(coach_with_model(message="22g 配方换成 15g", model="m", gateway=gw))
    assert out is not None and "225ml" in out
    # 自由文本走 chat，不应带 response_format。
    assert "response_format" not in gw.last_kwargs


def test_coach_sends_original_images_to_vision_model() -> None:
    gw = _FakeGateway("这张图能看到粉床中间略塌，但口味仍以你的描述为准。")
    out = asyncio.run(
        coach_with_model(
            message="这杯偏酸，帮我结合图看看下一杯怎么调",
            model="deepseek-chat",
            vision_model="kimi-k2.6",
            image_urls=[_IMG],
            gateway=gw,
        )
    )
    assert out and "粉床" in out
    assert gw.last_kwargs["model"] == "kimi-k2.6"
    user_msg = gw.last_kwargs["messages"][-1]
    assert isinstance(user_msg["content"], list)
    assert any(p.get("type") == "image_url" and p["image_url"]["url"] == _IMG for p in user_msg["content"])


def test_coach_empty_text_returns_none() -> None:
    out = asyncio.run(coach_with_model(message="x", model="m", gateway=_FakeGateway("   ")))
    assert out is None
