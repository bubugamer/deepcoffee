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


def test_bean_parse_none_when_gateway_disabled() -> None:
    assert asyncio.run(parse_bean_with_model("巴拿马 瑰夏", model="m", gateway=_DISABLED)) is None


def test_bean_parse_maps_fields_and_flavor() -> None:
    payload = json.dumps(
        {
            "name": "巴拿马 瑰夏 日晒",
            "roaster_name": "千峰",
            "bean_components": [
                {"origin_name": "巴拿马", "process_name": "日晒", "varietal_names": ["瑰夏"]}
            ],
            "flavor_notes": ["茉莉花香", "柑橘"],
            "evil_key": "drop me",
        }
    )
    draft = asyncio.run(parse_bean_with_model("...", model="m", gateway=_FakeGateway(payload)))
    assert draft is not None
    assert draft.bean_components[0].origin_name == "巴拿马"
    assert draft.bean_components[0].varietal_names == ["瑰夏"]
    assert draft.flavor.source == "user"
    assert "茉莉花香" in draft.flavor.notes


def test_bean_parse_captures_flavor_note_emojis() -> None:
    payload = json.dumps(
        {
            "name": "测试豆",
            "flavor_notes": ["荔枝", "柑橘"],
            # 含一个不在 notes 里的词，应被过滤掉
            "flavor_note_emojis": {"荔枝": "🥭", "柑橘": "🍊", "幽灵词": "❌"},
        }
    )
    draft = asyncio.run(parse_bean_with_model("...", model="m", gateway=_FakeGateway(payload)))
    assert draft is not None
    assert draft.flavor.note_emojis == {"荔枝": "🥭", "柑橘": "🍊"}


def test_bean_parse_without_emojis_defaults_empty() -> None:
    payload = json.dumps({"name": "测试豆", "flavor_notes": ["柑橘"]})
    draft = asyncio.run(parse_bean_with_model("...", model="m", gateway=_FakeGateway(payload)))
    assert draft is not None
    assert draft.flavor.note_emojis == {}


def test_bean_parse_invalid_json_returns_none() -> None:
    assert asyncio.run(parse_bean_with_model("x", model="m", gateway=_FakeGateway("nope"))) is None


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
    draft = asyncio.run(parse_brew_with_model("...", model="m", gateway=_FakeGateway(payload)))
    assert isinstance(draft, BrewDraft)
    assert draft.device == "V60"
    assert draft.dose_g == 15


def test_brew_parse_rejects_bad_value() -> None:
    # dose_g<=0 触发 BrewDraft 校验失败 → None（回退本地）。
    payload = json.dumps({"device": "V60", "dose_g": 0})
    assert asyncio.run(parse_brew_with_model("x", model="m", gateway=_FakeGateway(payload))) is None


def test_brew_parse_extracts_pour_stages_into_brew_steps() -> None:
    # 分段注水方案应解析进 brew_steps（冲煮阶段），不被塞进 notes（感官记录）。
    payload = json.dumps(
        {
            "bean_name": "苏丹汝魅",
            "device": "V60",
            "dose_g": 15,
            "water_ml": 240,
            "water_temp_c": 92,
            "brew_time_seconds": 150,
            "brew_steps": [
                {"time_seconds": 35, "action": "闷蒸，绕圈浸湿所有粉", "water_ml": 30, "note": None},
                {"time_seconds": 60, "action": "中心绕圈注水", "water_ml": 100, "note": "累计130ml"},
                {"time_seconds": 100, "action": "中心小绕圈注水", "water_ml": 110, "note": "累计240ml"},
            ],
            "notes": None,
        }
    )
    draft = asyncio.run(parse_brew_with_model("...", model="m", gateway=_FakeGateway(payload)))
    assert isinstance(draft, BrewDraft)
    assert len(draft.brew_steps) == 3
    assert draft.brew_steps[0].time_seconds == 35
    assert draft.brew_steps[1].water_ml == 100
    assert draft.brew_steps[2].action == "中心小绕圈注水"
    assert draft.notes is None  # 步骤没被塞进 notes


# --- brew_recap ------------------------------------------------------------

_DRAFT = BrewDraft(bean_name="耶加雪菲", device="V60", dose_g=15, water_ml=240, water_temp_c=92, brew_time_seconds=150)


def test_brew_recap_none_when_gateway_disabled() -> None:
    assert asyncio.run(recap_with_model(_DRAFT, model="m", gateway=_DISABLED)) is None


def test_brew_recap_parses() -> None:
    payload = json.dumps({"recap": "一杯均衡的耶加。", "suggestions": ["下次略调细研磨", "提高 1°C"]})
    result = asyncio.run(recap_with_model(_DRAFT, model="m", gateway=_FakeGateway(payload)))
    assert result is not None
    recap, suggestions = result
    assert recap == "一杯均衡的耶加。"
    assert len(suggestions) == 2


def test_brew_recap_empty_recap_returns_none() -> None:
    payload = json.dumps({"recap": "  ", "suggestions": []})
    assert asyncio.run(recap_with_model(_DRAFT, model="m", gateway=_FakeGateway(payload))) is None
