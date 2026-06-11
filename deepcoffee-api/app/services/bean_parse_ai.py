"""豆卡 AI 解析 bean_parse（§4）——模型抽取明确写出的客观豆卡字段。

**有模型用模型、没有就回退本地**：成功返回 BeanDraft，任何条件不满足/不合规返回 None，
调用方回退 `bean_parser.parse_bean_input`。模型只负责抽取，confidence / 补全卡片由后端生成。
"""

from __future__ import annotations

import logging

from app.prompts import BEAN_PARSE_SYSTEM
from app.schemas.bean import BeanDraft
from app.services.bean_parser import build_flavor
from app.services.model_gateway import ModelGateway, model_gateway
from app.services.model_json import chat_json

logger = logging.getLogger(__name__)

_BEAN_KEYS = [
    "name", "roaster_name", "roaster_product_name", "origin_name", "process_name",
    "varietal_names", "green_bean_merchant_name", "coffee_source_name", "flavor_notes",
]


def _str_list(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


async def parse_bean_with_model(
    text: str, *, token: str | None, model: str, gateway: ModelGateway | None = None
) -> BeanDraft | None:
    gw = gateway or model_gateway
    if not token or not gw.enabled:
        return None
    messages = [
        {"role": "system", "content": BEAN_PARSE_SYSTEM},
        {"role": "user", "content": text},
    ]
    try:
        data = await chat_json(
            gw, user_token=token, model=model, messages=messages,
            temperature=0, max_tokens=600, allowed_keys=_BEAN_KEYS,
        )
        return BeanDraft(
            name=data.get("name"),
            roaster_name=data.get("roaster_name"),
            roaster_product_name=data.get("roaster_product_name"),
            coffee_source_name=data.get("coffee_source_name"),
            green_bean_merchant_name=data.get("green_bean_merchant_name"),
            origin_name=data.get("origin_name"),
            process_name=data.get("process_name"),
            varietal_names=_str_list(data.get("varietal_names")),
            flavor=build_flavor(_str_list(data.get("flavor_notes"))),
            private_notes=None,
        )
    except Exception as exc:  # noqa: BLE001 — 抽取失败即回退本地，不影响建档
        logger.warning("bean_parse model failed, fallback local: %s", exc)
        return None
