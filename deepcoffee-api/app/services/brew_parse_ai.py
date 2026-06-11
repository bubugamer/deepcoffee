"""冲煮记录 AI 解析 brew_parse（§6）——模型抽取冲煮描述里明确写出的结构化字段。

**有模型用模型、没有就回退本地**：成功返回 BrewDraft（草稿，不写库），任何不合规返回 None，
调用方回退 `input_parser.parse_brew_input`。
"""

from __future__ import annotations

import logging

from app.prompts import BREW_PARSE_SYSTEM
from app.schemas.brew import BrewDraft
from app.services.model_gateway import ModelGateway, model_gateway
from app.services.model_json import chat_json, whitelist_keys

logger = logging.getLogger(__name__)

_BREW_KEYS = [
    "bean_name", "origin", "roaster", "process", "varietal", "device", "grinder",
    "grind_setting", "dose_g", "water_ml", "water_temp_c", "brew_time_seconds", "evaluation", "notes",
]


async def parse_brew_with_model(
    text: str, *, token: str | None, model: str, gateway: ModelGateway | None = None
) -> BrewDraft | None:
    gw = gateway or model_gateway
    if not token or not gw.enabled:
        return None
    messages = [
        {"role": "system", "content": BREW_PARSE_SYSTEM},
        {"role": "user", "content": text},
    ]
    try:
        data = await chat_json(
            gw, user_token=token, model=model, messages=messages,
            temperature=0, max_tokens=700, allowed_keys=_BREW_KEYS,
        )
        # 直接用 Pydantic 校验映射（含嵌套 evaluation）；非法值（如 dose_g<=0）会抛错 → 回退。
        return BrewDraft.model_validate(whitelist_keys(data, _BREW_KEYS))
    except Exception as exc:  # noqa: BLE001 — 抽取失败即回退本地
        logger.warning("brew_parse model failed, fallback local: %s", exc)
        return None
