"""冲煮教练 brew_coach（§8）——连续调参、缩放、刻度换算、养豆/器具建议等解释型问答。

默认**自由文本**（不走 JSON）。**有模型用模型、没有就回退本地保守建议**：模型不可用时，
保留已有方案、给「一次只调一个变量」的稳妥提示，绝不编造官方参数。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.prompts import BREW_COACH_SYSTEM, BREW_COACH_USER_TEMPLATE
from app.services.multimodal import build_user_content, image_unavailable_note, select_model_for_images
from app.services.model_gateway import ModelGateway, model_gateway

logger = logging.getLogger(__name__)

# 模型不可用时的本地保守兜底（§8 降级）。
LOCAL_COACH_FALLBACK = (
    "先按稳妥做法来：一次只调整研磨、水温、粉水比或注水方式中的一个变量，冲一杯观察再决定下一步。"
    "如果你告诉我这杯的口味反馈（偏酸 / 偏苦 / 甜感弱 / 醇厚不足 / 尾韵短），我可以给更具体的方向。"
)


def _as_text(value: Any) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return "（无）"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


async def coach_with_model(
    *,
    message: str,
    active_bean: Any = None,
    active_equipment: Any = None,
    active_recipe: Any = None,
    entity_inventory: Any = None,
    image_urls: list[str] | None = None,
    taste_feedback: Any = None,
    history: list[dict[str, str]] | None = None,
    model: str,
    vision_model: str | None = None,
    gateway: ModelGateway | None = None,
) -> str | None:
    """成功返回教练回复文本；网关不可用 / 出错返回 None（调用方用本地兜底）。"""
    gw = gateway or model_gateway
    if not gw.enabled:
        return None
    use_images = bool(image_urls and vision_model and gw.vision_enabled)
    image_context = (
        "本轮用户附带了原始图片。请直接查看图片，并判断图片是否能帮助回答当前冲煮问题；"
        "如果图片无关、看不清或不能支持结论，就说明不会依据图片判断，不要编造图片细节。"
        if use_images
        else image_unavailable_note(image_urls, vision_model)
    )
    user_content = BREW_COACH_USER_TEMPLATE.format(
        active_bean=_as_text(active_bean),
        active_equipment=_as_text(active_equipment),
        active_recipe=_as_text(active_recipe),
        entity_inventory=_as_text(entity_inventory),
        image_context=image_context,
        taste_feedback=_as_text(taste_feedback),
        message=message,
    )
    model_to_use = select_model_for_images(text_model=model, vision_model=vision_model if use_images else None, image_urls=image_urls)
    messages = [{"role": "system", "content": BREW_COACH_SYSTEM}]
    if history:
        messages.extend(history)
    messages.append(
        {"role": "user", "content": build_user_content(user_content, image_urls if use_images else None)}
    )
    try:
        result = await gw.chat(
            model=model_to_use, messages=messages, temperature=0.4, max_tokens=3000
        )
    except Exception as exc:  # noqa: BLE001 — 失败即回退本地保守建议
        logger.warning("brew_coach model failed, fallback local: %s", exc)
        return None
    text = (result.content or "").strip()
    return text or None
