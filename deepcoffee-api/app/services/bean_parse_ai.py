"""豆卡 AI 解析 bean_parse（§4）——模型抽取明确写出的客观豆卡字段。

**有模型用模型、没有就回退本地**：成功返回 BeanDraft，任何条件不满足/不合规返回 None，
调用方回退 `bean_parser.parse_bean_input`。模型只负责抽取，confidence / 补全卡片由后端生成。
"""

from __future__ import annotations

import logging

from app.prompts import BEAN_PARSE_SYSTEM
from app.schemas.bean import BeanComponent, BeanDraft
from app.services.bean_parser import build_flavor
from app.services.model_gateway import ModelGateway, model_gateway
from app.services.model_json import chat_json

logger = logging.getLogger(__name__)

_BEAN_KEYS = [
    "name", "roaster_name", "roaster_product_name", "origin_name", "process_name",
    "varietal_names", "green_bean_merchant_name", "coffee_source_name", "flavor_notes",
    "flavor_note_emojis",
    "altitude_text", "harvest_date_text", "roast_date_text", "net_weight_text", "bean_components",
]


def _str_list(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _str_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str) and v}


def _str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _components(value: object) -> list[BeanComponent]:
    if not isinstance(value, list):
        return []
    out: list[BeanComponent] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        out.append(
            BeanComponent(
                origin_name=_str(item.get("origin_name")),
                coffee_source_name=_str(item.get("coffee_source_name")),
                process_name=_str(item.get("process_name")),
                varietal_names=_str_list(item.get("varietal_names")),
                altitude_text=_str(item.get("altitude_text")),
                share_text=_str(item.get("share_text")),
                notes=_str(item.get("notes")),
            )
        )
    return out


async def parse_bean_with_model(
    text: str, *, model: str, gateway: ModelGateway | None = None
) -> BeanDraft | None:
    gw = gateway or model_gateway
    if not gw.enabled:
        return None
    messages = [
        {"role": "system", "content": BEAN_PARSE_SYSTEM},
        {"role": "user", "content": text},
    ]
    try:
        data = await chat_json(
            gw, model=model, messages=messages,
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
            altitude_text=_str(data.get("altitude_text")),
            harvest_date_text=_str(data.get("harvest_date_text")),
            roast_date_text=_str(data.get("roast_date_text")),
            net_weight_text=_str(data.get("net_weight_text")),
            bean_components=_components(data.get("bean_components")),
            flavor=build_flavor(_str_list(data.get("flavor_notes")), _str_dict(data.get("flavor_note_emojis"))),
            private_notes=None,
        )
    except Exception as exc:  # noqa: BLE001 — 抽取失败即回退本地，不影响建档
        logger.warning("bean_parse model failed, fallback local: %s", exc)
        return None
