"""图片理解 image_understanding（§2）——把豆卡 / 粉床 / 器具图转成结构化上下文。

外部依赖（单列）：默认模型 deepseek-v4-pro 不支持图片输入，本能力依赖一个**可配置的
vision 通道**（`settings.new_api_vision_model`，默认 Moonshot `kimi-k2.6`，多模态、OpenAI
兼容）。图片以 **base64 data URI 经 `image_url` 分块传入**（Moonshot 不接受纯 URL）。
通道未配置 / 无 token / 没有可用图片时，整体降级返回 None——调用方据此提示用户「粘贴卡片
文字」，不假装识别成功。

设计与全局约定一致：有通道用通道、没有就降级；任何不合规返回 None，绝不编造识别结果。
对应 docs/deepcoffee-ai-prompts.md §2。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.prompts import IMAGE_UNDERSTANDING_SYSTEM, IMAGE_UNDERSTANDING_USER_TEMPLATE
from app.services.multimodal import build_user_content, to_data_url
from app.services.model_gateway import ModelGateway, model_gateway
from app.services.model_json import chat_json

logger = logging.getLogger(__name__)

# §2 提示词约定的 JSON 顶层键。
IMAGE_KEYS: list[str] = [
    "image_type",
    "ocr_text",
    "bean_fields",
    "brew_photo_assessment",
    "equipment_fields",
    "confidence",
    "uncertainties",
    "suggested_next_actions",
]
_IMAGE_TYPES = frozenset({"bean_card", "brew_photo", "equipment_photo", "unknown"})


def _as_text(value: Any) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return "（无）"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


async def understand_image(
    *,
    message: str,
    images: list[str] | None,
    session_state: dict | None = None,
    token: str | None,
    vision_model: str | None,
    gateway: ModelGateway | None = None,
) -> dict | None:
    """成功返回结构化图片理解 JSON；通道未配 / 无 token / 无图片 / 不合规返回 None。

    `images`：base64 data URI 列表（`data:image/...;base64,...`），直接以 image_url 分块喂给
    vision 模型。
    """
    gw = gateway or model_gateway
    if not token or not gw.enabled or not vision_model or not images:
        return None
    user_text = IMAGE_UNDERSTANDING_USER_TEMPLATE.format(
        message=message or "",
        image_or_ocr_payload="（见随附图片）",
        session_state=_as_text(session_state),
    )
    messages = [
        {"role": "system", "content": IMAGE_UNDERSTANDING_SYSTEM},
        {"role": "user", "content": build_user_content(user_text, images)},
    ]
    try:
        data = await chat_json(
            gw,
            user_token=token,
            model=vision_model,
            messages=messages,
            # kimi-k2.6 关思考（instant 模式）→ 直接出结构化 JSON、不绕思维链，更快更省；
            # 非思考模式温度用 0.6（思考模式才强制 1）。thinking 开关是 Moonshot 专有参数。
            temperature=0.6,
            max_tokens=2048,
            required_keys=["image_type"],
            allowed_keys=IMAGE_KEYS,
            extra_body={"thinking": {"type": "disabled"}},
        )
    except Exception as exc:  # noqa: BLE001 — 识别失败即降级，让用户贴文字
        logger.warning("image_understanding failed, degrade: %s", exc)
        return None
    if data.get("image_type") not in _IMAGE_TYPES:
        logger.warning("image_understanding returned unknown image_type %r, degrade", data.get("image_type"))
        return None
    return data
