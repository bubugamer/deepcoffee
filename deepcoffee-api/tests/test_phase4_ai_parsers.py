from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.schemas.brew import BrewDraft
from app.services.bean_parse_ai import parse_bean_with_model
from app.services.brew_parse_ai import parse_brew_with_model
from app.services.brew_recap_ai import recap_with_model


class _FakeGateway:
    enabled = True

    def __init__(self, content: str) -> None:
        self.content = content
        self.last_kwargs: dict = {}

    async def chat(self, **kwargs):  # noqa: ANN003
        self.last_kwargs = kwargs
        return SimpleNamespace(content=self.content, model="fake")


_DISABLED = SimpleNamespace(enabled=False)


# --- bean_parse ------------------------------------------------------------

def test_bean_parse_none_without_token() -> None:
    assert asyncio.run(parse_bean_with_model("巴拿马 瑰夏", token=None, model="m", gateway=_FakeGateway("{}"))) is None


def test_bean_parse_none_when_gateway_disabled() -> None:
    assert asyncio.run(parse_bean_with_model("巴拿马 瑰夏", token="sk", model="m", gateway=_DISABLED)) is None


def test_bean_parse_maps_fields_and_flavor() -> None:
    payload = json.dumps(
        {
            "name": "巴拿马 瑰夏 日晒",
            "roaster_name": "千峰",
            "origin_name": "巴拿马",
            "process_name": "日晒",
            "varietal_names": ["瑰夏"],
            "flavor_notes": ["茉莉花香", "柑橘"],
            "evil_key": "drop me",
        }
    )
    draft = asyncio.run(parse_bean_with_model("...", token="sk", model="m", gateway=_FakeGateway(payload)))
    assert draft is not None
    assert draft.origin_name == "巴拿马"
    assert draft.varietal_names == ["瑰夏"]
    assert draft.flavor.source == "user"
    assert "茉莉花香" in draft.flavor.notes


def test_bean_parse_invalid_json_returns_none() -> None:
    assert asyncio.run(parse_bean_with_model("x", token="sk", model="m", gateway=_FakeGateway("nope"))) is None


# --- brew_parse ------------------------------------------------------------

def test_brew_parse_none_without_token() -> None:
    assert asyncio.run(parse_brew_with_model("V60 15g", token=None, model="m", gateway=_FakeGateway("{}"))) is None


def test_brew_parse_maps_fields() -> None:
    payload = json.dumps(
        {
            "bean_name": "耶加雪菲",
            "device": "V60",
            "grinder": "C40",
            "grind_setting": "#18",
            "dose_g": 15,
            "water_ml": 240,
            "water_temp_c": 92,
            "brew_time_seconds": 150,
            "notes": "柑橘明亮",
        }
    )
    draft = asyncio.run(parse_brew_with_model("...", token="sk", model="m", gateway=_FakeGateway(payload)))
    assert isinstance(draft, BrewDraft)
    assert draft.device == "V60"
    assert draft.dose_g == 15


def test_brew_parse_rejects_bad_value() -> None:
    # dose_g<=0 触发 BrewDraft 校验失败 → None（回退本地）。
    payload = json.dumps({"device": "V60", "dose_g": 0})
    assert asyncio.run(parse_brew_with_model("x", token="sk", model="m", gateway=_FakeGateway(payload))) is None


# --- brew_recap ------------------------------------------------------------

_DRAFT = BrewDraft(bean_name="耶加雪菲", device="V60", dose_g=15, water_ml=240, water_temp_c=92, brew_time_seconds=150)


def test_brew_recap_none_without_token() -> None:
    assert asyncio.run(recap_with_model(_DRAFT, token=None, model="m", gateway=_FakeGateway("{}"))) is None


def test_brew_recap_parses() -> None:
    payload = json.dumps({"recap": "一杯均衡的耶加。", "suggestions": ["下次略调细研磨", "提高 1°C"]})
    result = asyncio.run(recap_with_model(_DRAFT, token="sk", model="m", gateway=_FakeGateway(payload)))
    assert result is not None
    recap, suggestions = result
    assert recap == "一杯均衡的耶加。"
    assert len(suggestions) == 2


def test_brew_recap_empty_recap_returns_none() -> None:
    payload = json.dumps({"recap": "  ", "suggestions": []})
    assert asyncio.run(recap_with_model(_DRAFT, token="sk", model="m", gateway=_FakeGateway(payload))) is None
