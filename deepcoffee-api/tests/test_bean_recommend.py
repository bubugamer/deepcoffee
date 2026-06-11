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

    async def chat(self, **kwargs):  # noqa: ANN003
        return SimpleNamespace(content=self.content, model="fake")


def _run(gateway=None, token="sk-x", **overrides):
    kwargs = dict(
        bean=_bean(),
        equipment_profiles=[],
        equipment_draft=None,
        message="给我一个方案",
        session_id="sess_1",
        status="needs_input",
        token=token,
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
        "equipment": {"brew_method": None, "grinder": None, "filter_media": None, "water": None},
        "missing_fields": ["brew_method", "grinder", "filter_media"],
        "recommendation": None,
    }
)

_COMPLETED = json.dumps(
    {
        "status": "completed",
        "intent": "generate_recommendation",
        "assistant_message": "器具够了，给你一组起手参数。",
        "equipment": {"brew_method": "V60", "grinder": "C40", "filter_media": "Hario 滤纸", "water": None},
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
    assert set(turn.missing_fields) == {"brew_method", "grinder", "filter_media"}
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


def test_no_token_local_completes_with_complete_draft() -> None:
    turn = _run(
        token=None,
        gateway=_FakeGateway(_COMPLETED),
        equipment_draft={"brew_method": "Origami", "grinder": "ZP6", "filter_media": "锥形滤纸"},
    )
    assert turn.status == "completed"
    assert turn.source == "local"
    assert turn.recommendation["device"] == "Origami"


def test_no_token_no_equipment_fallback() -> None:
    turn = _run(token=None, gateway=_FakeGateway(_COMPLETED))
    assert turn.status == "fallback"
    assert turn.missing_fields
