"""用户记忆抽取（L3）：从最近对话 + 冲煮记录抽稳定偏好 / 事实。

设计同全局约定：有模型用模型、没有就不抽（返回 []）。本服务只产出候选条目，
去重 / 落库由调用方经 ``user_memory_repository.upsert`` 完成。绝不抛业务异常打断对话。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.prompts import MEMORY_EXTRACT_SYSTEM, MEMORY_EXTRACT_USER_TEMPLATE
from app.services.model_gateway import ModelGateway, model_gateway
from app.services.model_json import ModelJSONError, chat_json

logger = logging.getLogger(__name__)

_ALLOWED_KINDS = frozenset({"taste", "equipment", "habit", "goal", "fact"})


def _as_text(value: Any) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return "（无）"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


async def extract_memories(
    *,
    recent_dialog: Any = None,
    recent_brews: Any = None,
    existing_memories: Any = None,
    model: str,
    gateway: ModelGateway | None = None,
) -> list[dict[str, Any]]:
    """返回候选记忆条目 ``[{kind, content, confidence}]``；网关不可用 / 失败 / 无内容时返回 []。"""
    gw = gateway or model_gateway
    if not gw.enabled:
        return []
    user_content = MEMORY_EXTRACT_USER_TEMPLATE.format(
        recent_dialog=_as_text(recent_dialog),
        recent_brews=_as_text(recent_brews),
        existing_memories=_as_text(existing_memories),
    )
    messages = [
        {"role": "system", "content": MEMORY_EXTRACT_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    try:
        data = await chat_json(
            gw,
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=600,
            required_keys=["memories"],
            allowed_keys=["memories"],
        )
    except ModelJSONError as exc:
        logger.warning("memory_extract JSON invalid, skip: %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001 — 抽取失败不影响对话
        logger.warning("memory_extract model call failed, skip: %s", exc)
        return []

    items = data.get("memories")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        kind = it.get("kind")
        raw_content = it.get("content")
        content = raw_content.strip() if isinstance(raw_content, str) else ""
        if kind not in _ALLOWED_KINDS or not content:
            continue
        conf = it.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else 0.6
        out.append({"kind": kind, "content": content, "confidence": max(0.0, min(1.0, conf))})
    return out
