"""Coffea 建议冲煮参数 · 多轮闭环（docs/deepcoffee-ai-prompts.md §5）。

「询问器具 → 抽取器具 JSON → 信息够了生成建议」的一轮评估。**有模型用模型、没有回退本地**：
- 模型路径：用 §5 提示词调 JSON 模式，校验状态/意图/器具白名单/参数范围与自洽，任何不合规返回 None。
- 本地兜底：器具齐（来自草稿或已存档的整套器具）就本地启发式生成 completed；不齐则 fallback，
  只提示补器具，**绝不默认 V60**。

本服务只产「这一轮的结果」（RecommendTurn）；保存器具资料、落隐藏 ai_suggestion 记录由端点做。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.prompts import BEAN_RECOMMEND_SYSTEM, BEAN_RECOMMEND_USER_TEMPLATE
from app.schemas.bean import Bean
from app.schemas.brew import BrewDraft
from app.services.brew_validation import complete_brew_parameters
from app.services.grinder_scales import format_grinder_reference, lookup_grinder_scale
from app.services.model_gateway import ModelGateway, model_gateway
from app.services.model_json import chat_json, check_number_in_range, whitelist_keys
from app.services.recommend_service import generate_recommended_params

logger = logging.getLogger(__name__)

REQUIRED_EQUIPMENT = ["dripper", "grinder", "filter_media"]
_EQUIPMENT_KEYS = ["dripper", "brew_method", "grinder", "filter_media", "water"]
_PLAN_KEYS = ["status", "intent", "assistant_message", "equipment", "missing_fields", "recommendation"]
_REC_KEYS = [
    "device", "grinder", "filter", "dose_g", "water_ml", "water_temp_c",
    "ratio", "grind_setting", "brew_time_seconds", "notes",
]
WATER_TEMP_MIN, WATER_TEMP_MAX = 85.0, 96.0


@dataclass
class RecommendTurn:
    status: str  # needs_input / completed / fallback
    assistant_message: str
    equipment: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    recommendation: dict[str, Any] | None = None
    intent: str | None = None
    source: str = "model"


def _as_text(value: Any) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return "（无）"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _merge_equipment(*sources: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {key: None for key in _EQUIPMENT_KEYS}
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in _EQUIPMENT_KEYS:
            value = src.get(key)
            if value:
                merged[key] = value
    return merged


def _missing(equipment: dict[str, Any]) -> list[str]:
    return [key for key in REQUIRED_EQUIPMENT if not equipment.get(key)]


def _first_complete_profile(profiles: list[dict[str, Any]]) -> dict[str, Any] | None:
    """优先返回必填齐全的默认套（is_default），其次第一套齐全的。"""
    complete = [p for p in profiles or [] if all(p.get(key) for key in REQUIRED_EQUIPMENT)]
    for profile in complete:
        if profile.get("is_default"):
            return {key: profile.get(key) for key in _EQUIPMENT_KEYS}
    if complete:
        return {key: complete[0].get(key) for key in _EQUIPMENT_KEYS}
    return None


def _validate_recommendation(rec: dict[str, Any], equipment: dict[str, Any]) -> dict[str, Any] | None:
    """校验模型给的 recommendation：水温范围 + dose/water/ratio 自洽。不合规返回 None。"""
    try:
        rec = whitelist_keys(rec, _REC_KEYS)
        temp = check_number_in_range(
            rec.get("water_temp_c"), field="water_temp_c", low=WATER_TEMP_MIN, high=WATER_TEMP_MAX
        )
        draft = BrewDraft(
            device=equipment.get("dripper") or rec.get("device"),
            grinder=equipment.get("grinder") or rec.get("grinder"),
            grind_setting=rec.get("grind_setting"),
            dose_g=rec.get("dose_g"),
            water_ml=rec.get("water_ml"),
            water_temp_c=temp,
            ratio=rec.get("ratio"),
            brew_time_seconds=rec.get("brew_time_seconds"),
            notes=rec.get("notes"),
        )
        draft = complete_brew_parameters(draft)  # <2 of dose/water/ratio → AppError → 视为不合规
    except Exception as exc:  # noqa: BLE001 — 任何校验失败即不合规 → 上层降级
        logger.warning("recommend validation failed, treat as fallback: %s", exc)
        return None
    return _recommendation_from_draft(draft, equipment, rec.get("filter"))


def _recommendation_from_draft(draft: BrewDraft, equipment: dict[str, Any], filter_hint: str | None) -> dict[str, Any]:
    return {
        "device": draft.device,
        "grinder": draft.grinder,
        "filter": equipment.get("filter_media") or filter_hint,
        "dose_g": draft.dose_g,
        "water_ml": draft.water_ml,
        "water_temp_c": draft.water_temp_c,
        "ratio": draft.ratio,
        "grind_setting": draft.grind_setting,
        "brew_time_seconds": draft.brew_time_seconds,
        "notes": draft.notes,
    }


async def _model_turn(
    *,
    bean: Bean,
    equipment_profiles: list[dict[str, Any]],
    equipment_draft: dict[str, Any] | None,
    message: str | None,
    session_id: str,
    status: str,
    model: str,
    gateway: ModelGateway,
) -> RecommendTurn | None:
    grinder_names = [p.get("grinder") for p in equipment_profiles or []]
    if isinstance(equipment_draft, dict):
        grinder_names.append(equipment_draft.get("grinder"))
    user_content = BEAN_RECOMMEND_USER_TEMPLATE.format(
        session_id=session_id,
        status=status,
        name=bean.name,
        origin=bean.origin or "（未知）",
        process=bean.process or "（未知）",
        varietal="、".join(bean.varietal) or "（未知）",
        flavor_notes="、".join(bean.flavor.notes) if bean.flavor and bean.flavor.notes else "（未知）",
        equipment_profiles=_as_text(equipment_profiles),
        grinder_reference=format_grinder_reference(grinder_names),
        equipment_draft=_as_text(equipment_draft),
        message=message or "（用户未补充文字，请基于已有信息起手）",
    )
    messages = [
        {"role": "system", "content": BEAN_RECOMMEND_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    try:
        data = await chat_json(
            gateway,
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=3000,
            required_keys=["status"],
            allowed_keys=_PLAN_KEYS,
        )
    except Exception as exc:  # noqa: BLE001 — 模型/JSON 失败即回退本地
        logger.warning("bean_recommend model failed, fallback local: %s", exc)
        return None

    status_out = data.get("status")
    if status_out not in {"needs_input", "completed"}:
        return None
    raw_equipment = data.get("equipment")
    equipment = _merge_equipment(raw_equipment if isinstance(raw_equipment, dict) else {})
    missing = [m for m in (data.get("missing_fields") or []) if m in REQUIRED_EQUIPMENT]
    assistant_message = data.get("assistant_message") if isinstance(data.get("assistant_message"), str) else ""
    intent = data.get("intent") if isinstance(data.get("intent"), str) else None

    if status_out == "needs_input":
        return RecommendTurn(
            status="needs_input",
            intent=intent or "ask_equipment",
            assistant_message=assistant_message or "先确认一下器具：你用什么冲煮方式、哪台磨豆机、什么过滤介质？",
            equipment=equipment,
            missing_fields=missing or _missing(equipment),
            source="model",
        )

    # completed：器具必须真齐 + recommendation 必须通过范围/自洽校验，否则不可信 → 降级。
    if _missing(equipment):
        return None
    rec = data.get("recommendation")
    validated = _validate_recommendation(rec, equipment) if isinstance(rec, dict) else None
    if validated is None:
        return None
    return RecommendTurn(
        status="completed",
        intent=intent or "generate_recommendation",
        assistant_message=assistant_message or "器具信息够了，先按这套器具给你一组稳定起手参数。",
        equipment=equipment,
        missing_fields=[],
        recommendation=validated,
        source="model",
    )


def _local_turn(
    bean: Bean,
    equipment_profiles: list[dict[str, Any]],
    equipment_draft: dict[str, Any] | None,
) -> RecommendTurn:
    draft_equipment = _merge_equipment(equipment_draft)
    use = draft_equipment if not _missing(draft_equipment) else _first_complete_profile(equipment_profiles)
    if use:
        params, _note = generate_recommended_params(bean)
        updates: dict[str, Any] = {"device": use["dripper"], "grinder": use["grinder"]}
        # 磨豆机命中刻度表时给具体区间，替换本地启发式的「中度」。
        scale = lookup_grinder_scale(use.get("grinder"))
        if scale is not None:
            updates["grind_setting"] = scale.medium_ref
        params = params.model_copy(update=updates)
        return RecommendTurn(
            status="completed",
            intent="generate_recommendation",
            assistant_message="先按你这套器具给一组稳定的起手参数（当前由本地规则生成）。",
            equipment=use,
            missing_fields=[],
            recommendation=_recommendation_from_draft(params, use, None),
            source="local",
        )
    return RecommendTurn(
        status="fallback",
        intent="ask_equipment",
        assistant_message="我先记下了。要生成方案，请告诉我滤杯（冲煮器具）、磨豆机和过滤介质。",
        equipment=draft_equipment,
        missing_fields=_missing(draft_equipment),
        source="local",
    )


async def evaluate_turn(
    *,
    bean: Bean,
    equipment_profiles: list[dict[str, Any]],
    equipment_draft: dict[str, Any] | None,
    message: str | None,
    session_id: str,
    status: str,
    model: str,
    gateway: ModelGateway | None = None,
) -> RecommendTurn:
    gw = gateway or model_gateway
    if gw.enabled:
        turn = await _model_turn(
            bean=bean,
            equipment_profiles=equipment_profiles,
            equipment_draft=equipment_draft,
            message=message,
            session_id=session_id,
            status=status,
            model=model,
            gateway=gw,
        )
        if turn is not None:
            return turn
    return _local_turn(bean, equipment_profiles, equipment_draft)
