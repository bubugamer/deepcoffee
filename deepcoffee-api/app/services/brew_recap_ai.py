"""冲煮 AI 复盘 brew_recap（§7）——按已记录的参数/评分/备注给简短复盘 + 下次建议。

**有模型用模型、没有就回退本地**：成功返回 (recap, suggestions)，任何不合规返回 None，
调用方回退 `recap_service.build_local_recap`。只依据记录里有的信息，不编造风味/缺陷。
"""

from __future__ import annotations

import logging

from app.prompts import BREW_RECAP_SYSTEM, BREW_RECAP_USER_TEMPLATE
from app.schemas.brew import BrewDraft
from app.services.model_gateway import ModelGateway, model_gateway
from app.services.model_json import chat_json

logger = logging.getLogger(__name__)

_SUB_LABELS = [
    ("香气", "aroma"), ("风味", "flavor"), ("余韵", "aftertaste"),
    ("酸质", "acidity"), ("醇厚", "body"), ("平衡", "balance"),
]


def _format_user(draft: BrewDraft) -> str:
    ev = draft.evaluation
    overall = ev.overall.score if ev and ev.overall and ev.overall.score is not None else "无"
    sub_parts: list[str] = []
    if ev:
        for label, attr in _SUB_LABELS:
            item = getattr(ev, attr, None)
            if item and item.score is not None:
                sub_parts.append(f"{label} {item.score}")
    return BREW_RECAP_USER_TEMPLATE.format(
        bean_name=draft.bean_name or "未命名",
        process=draft.process or "未知",
        varietal=draft.varietal or "未知",
        device=draft.device or "未知",
        grinder=draft.grinder or "未知",
        grind_setting=draft.grind_setting or "未知",
        dose_g=draft.dose_g if draft.dose_g is not None else "?",
        water_ml=draft.water_ml if draft.water_ml is not None else "?",
        ratio=draft.ratio or "?",
        water_temp_c=draft.water_temp_c if draft.water_temp_c is not None else "?",
        brew_time_seconds=draft.brew_time_seconds if draft.brew_time_seconds is not None else "?",
        overall=overall,
        分项评分=("、".join(sub_parts) or "无"),
        notes=draft.notes or "无",
    )


async def recap_with_model(
    draft: BrewDraft, *, model: str, gateway: ModelGateway | None = None
) -> tuple[str, list[str]] | None:
    gw = gateway or model_gateway
    if not gw.enabled:
        return None
    messages = [
        {"role": "system", "content": BREW_RECAP_SYSTEM},
        {"role": "user", "content": _format_user(draft)},
    ]
    try:
        data = await chat_json(
            gw, model=model, messages=messages,
            temperature=0.5, max_tokens=500, required_keys=["recap"], allowed_keys=["recap", "suggestions"],
        )
    except Exception as exc:  # noqa: BLE001 — 复盘失败即回退本地模板
        logger.warning("brew_recap model failed, fallback local: %s", exc)
        return None
    recap = data.get("recap")
    if not isinstance(recap, str) or not recap.strip():
        return None
    suggestions = [s for s in (data.get("suggestions") or []) if isinstance(s, str)]
    return recap.strip(), suggestions[:3]
