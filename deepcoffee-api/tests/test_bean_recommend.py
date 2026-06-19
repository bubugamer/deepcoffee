from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app.schemas.bean import Bean, BeanFlavor
from app.services.bean_recommend_service import evaluate_turn


def _bean(process: str = "日晒", varietal: list[str] | None = None) -> Bean:
    now = datetime.now(timezone.utc)
    return Bean(
        bean_id="b1",
        name="测试豆 日晒",
        process=process,
        varietal=varietal or [],
        flavor=BeanFlavor(),
        created_at=now,
        updated_at=now,
    )


class _FakeGateway:
    enabled = True

    def __init__(self, content: str) -> None:
        self.content = content
        self.last_messages: list[dict] | None = None

    async def chat(self, **kwargs):  # noqa: ANN003
        self.last_messages = kwargs.get("messages")
        return SimpleNamespace(content=self.content, model="fake")


def _run(gateway=None, **overrides):
    kwargs = dict(
        bean=_bean(),
        equipment_profiles=[],
        equipment_draft=None,
        message="给我一个方案",
        session_id="sess_1",
        status="needs_input",
        model="m",
        gateway=gateway,
    )
    kwargs.update(overrides)
    return asyncio.run(evaluate_turn(**kwargs))


_NEEDS_INPUT = json.dumps(
    {
        "status": "needs_input",
        "intent": "ask_equipment",
        "assistant_message": "你用什么冲煮方式、磨豆机、过滤介质？",
        "equipment": {"dripper": None, "grinder": None, "filter_media": None, "water": None},
        "missing_fields": ["dripper", "grinder", "filter_media"],
        "recommendation": None,
    }
)

_COMPLETED = json.dumps(
    {
        "status": "completed",
        "intent": "generate_recommendation",
        "assistant_message": "器具够了，给你一组起手参数。",
        "equipment": {"dripper": "V60", "grinder": "C40", "filter_media": "Hario 滤纸", "water": None},
        "missing_fields": [],
        "recommendation": {
            "device": "V60",
            "grinder": "C40",
            "filter": "Hario 滤纸",
            "dose_g": 15,
            "water_ml": 240,
            "water_temp_c": 92,
            "ratio": "1:16",
            "grind_setting": "中度偏细",
            "brew_time_seconds": 160,
            "notes": "稳定起手参数",
        },
    }
)


def test_model_needs_input() -> None:
    turn = _run(gateway=_FakeGateway(_NEEDS_INPUT))
    assert turn.status == "needs_input"
    assert turn.source == "model"
    assert set(turn.missing_fields) == {"dripper", "grinder", "filter_media"}
    assert turn.recommendation is None


def test_model_completed_valid() -> None:
    turn = _run(gateway=_FakeGateway(_COMPLETED))
    assert turn.status == "completed"
    assert turn.source == "model"
    assert turn.recommendation["device"] == "V60"
    assert turn.recommendation["water_temp_c"] == 92
    # dose/water/ratio 已自洽。
    assert turn.recommendation["water_ml"] == 240


def test_model_out_of_range_temp_falls_back() -> None:
    bad = json.loads(_COMPLETED)
    bad["recommendation"]["water_temp_c"] = 120  # 越界 → 校验拒绝 → 降级
    turn = _run(gateway=_FakeGateway(json.dumps(bad)))
    # 模型结果被拒 → 本地兜底；无器具上下文 → fallback。
    assert turn.status == "fallback"
    assert turn.source == "local"


def test_model_completed_but_missing_equipment_falls_back() -> None:
    bad = json.loads(_COMPLETED)
    bad["equipment"]["grinder"] = None  # 声称完成但器具不全 → 不可信
    turn = _run(gateway=_FakeGateway(json.dumps(bad)))
    assert turn.status == "fallback"


def test_invalid_json_falls_back() -> None:
    turn = _run(gateway=_FakeGateway("not json"))
    assert turn.status == "fallback"
    assert turn.source == "local"


def test_local_completes_with_complete_draft() -> None:
    turn = _run(
        gateway=None,
        equipment_draft={"dripper": "Origami", "grinder": "ZP6", "filter_media": "锥形滤纸"},
    )
    assert turn.status == "completed"
    assert turn.source == "local"
    assert turn.recommendation["device"] == "Origami"


def test_local_no_equipment_fallback() -> None:
    turn = _run(gateway=None)
    assert turn.status == "fallback"
    assert turn.missing_fields


def test_local_prefers_default_profile() -> None:
    # 单件库存中，各必填类别都有默认项时，本地兜底直接使用默认项。
    turn = _run(
        gateway=None,
        equipment_profiles=[
            {"category": "brewer", "name": "V60", "is_default": False},
            {"category": "brewer", "name": "Orea", "is_default": True},
            {"category": "grinder", "name": "ZP6S", "is_default": True},
            {"category": "filter_media", "name": "锥形滤纸", "is_default": True},
        ],
    )
    assert turn.status == "completed"
    assert turn.source == "local"
    assert turn.recommendation["device"] == "Orea"


def test_local_missing_category_default_fallback() -> None:
    turn = _run(
        gateway=None,
        equipment_profiles=[
            {"category": "brewer", "name": "V60", "is_default": True},
            {"category": "grinder", "name": "C40", "is_default": True},
            {"category": "filter_media", "name": "纸滤", "is_default": False},
        ],
    )
    assert turn.status == "fallback"
    assert turn.equipment["dripper"] == "V60"
    assert turn.equipment["grinder"] == "C40"
    assert turn.missing_fields == ["filter_media"]


def test_local_grind_setting_from_scale_table() -> None:
    # 磨豆机命中刻度表 → grind_setting 用表中的中度参考区间，而不是「中度」。
    turn = _run(
        gateway=None,
        equipment_draft={"dripper": "Orea", "grinder": "1zpresso ZP6S 特调版", "filter_media": "锥形滤纸"},
    )
    assert turn.status == "completed"
    assert turn.recommendation["grind_setting"] == "4.5–5.5 圈（中度偏粗）"


def test_local_grind_setting_unknown_grinder_keeps_relative() -> None:
    turn = _run(
        gateway=None,
        equipment_draft={"dripper": "V60", "grinder": "无名小磨", "filter_media": "纸滤"},
    )
    assert turn.status == "completed"
    assert turn.recommendation["grind_setting"] == "中度"


def test_model_prompt_includes_grinder_reference() -> None:
    gateway = _FakeGateway(_COMPLETED)
    _run(
        gateway=gateway,
        equipment_profiles=[
            {"category": "brewer", "name": "V60", "is_default": True},
            {"category": "grinder", "name": "Comandante C40", "is_default": True},
            {"category": "filter_media", "name": "纸滤", "is_default": True},
        ],
    )
    user_content = gateway.last_messages[1]["content"]
    assert "磨豆机刻度参考资料" in user_content
    assert "Comandante C40" in user_content
    assert "22–26 格" in user_content
    # is_default 也注入了器具资料段
    assert '"is_default": true' in user_content


def test_model_prompt_unknown_grinder_no_reference() -> None:
    gateway = _FakeGateway(_COMPLETED)
    _run(
        gateway=gateway,
        equipment_profiles=[
            {"category": "brewer", "name": "V60", "is_default": True},
            {"category": "grinder", "name": "无名小磨", "is_default": True},
            {"category": "filter_media", "name": "纸滤", "is_default": True},
        ],
    )
    user_content = gateway.last_messages[1]["content"]
    assert "（无内置刻度资料）" in user_content
