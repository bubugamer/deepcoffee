from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.services.image_understanding import to_data_url, understand_image

_IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="


class _FakeGateway:
    enabled = True
    vision_enabled = True

    def __init__(self, content: str) -> None:
        self.content = content
        self.last_kwargs: dict = {}

    async def chat(self, **kwargs):  # noqa: ANN003
        self.last_kwargs = kwargs
        return SimpleNamespace(content=self.content, model="vision-fake")


_VALID = json.dumps(
    {
        "image_type": "bean_card",
        "ocr_text": ["巴拿马 瑰夏 日晒"],
        "bean_fields": {
            "name": "巴拿马 瑰夏 日晒",
            "bean_components": [{"origin_name": "巴拿马", "process_name": "日晒", "varietal_names": ["瑰夏"]}],
        },
        "brew_photo_assessment": None,
        "equipment_fields": None,
        "confidence": 0.8,
        "uncertainties": [],
        "suggested_next_actions": ["create_or_update_bean_card"],
    }
)


def _call(**overrides):
    kwargs = dict(
        message="看看这张豆卡",
        images=[_IMG],
        vision_model="kimi-k2.6",
        gateway=_FakeGateway(_VALID),
    )
    kwargs.update(overrides)
    return asyncio.run(understand_image(**kwargs))


# --- to_data_url ------------------------------------------------------------

def test_to_data_url_passthrough() -> None:
    assert to_data_url(data_url=_IMG) == _IMG


def test_to_data_url_from_base64() -> None:
    assert to_data_url(image_base64="QUJD", mime_type="image/png") == "data:image/png;base64,QUJD"


def test_to_data_url_defaults_mime() -> None:
    assert to_data_url(image_base64="QUJD") == "data:image/jpeg;base64,QUJD"


def test_to_data_url_none() -> None:
    assert to_data_url() is None
    assert to_data_url(data_url="http://x/y.png") is None  # 纯 URL 不算 data URI


# --- understand_image degrade paths ----------------------------------------

def test_degrades_without_vision_model() -> None:
    assert _call(vision_model=None) is None


def test_degrades_without_images() -> None:
    assert _call(images=[]) is None


def test_degrades_when_gateway_disabled() -> None:
    assert _call(gateway=SimpleNamespace(enabled=False, vision_enabled=False)) is None


# --- understand_image happy path + multimodal wire shape -------------------

def test_parses_valid_payload() -> None:
    data = _call()
    assert data is not None
    assert data["image_type"] == "bean_card"
    assert data["bean_fields"]["bean_components"][0]["process_name"] == "日晒"


def test_sends_multimodal_image_url() -> None:
    gw = _FakeGateway(_VALID)
    _call(gateway=gw)
    # vision 模型名 + 多模态分块（含 image_url base64）传到底层网关。
    assert gw.last_kwargs["model"] == "kimi-k2.6"
    user_msg = gw.last_kwargs["messages"][-1]
    assert isinstance(user_msg["content"], list)
    image_parts = [p for p in user_msg["content"] if p.get("type") == "image_url"]
    assert image_parts and image_parts[0]["image_url"]["url"] == _IMG


def test_rejects_unknown_image_type() -> None:
    assert _call(gateway=_FakeGateway(json.dumps({"image_type": "spaceship"}))) is None


def test_invalid_json_degrades() -> None:
    assert _call(gateway=_FakeGateway("not json")) is None
