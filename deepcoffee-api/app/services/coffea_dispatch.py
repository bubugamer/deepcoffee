"""Coffea 会话调度器（coffea_dispatch）——识别意图、规划下一步调用哪些专项能力。

设计与全局约定一致：**有模型用模型、没有就回退本地**。
- 模型路径：用 §1 的提示词调 JSON 模式，校验意图白名单与计划键，任何不合规返回 None。
- 本地兜底：按 §1「降级」的简单规则给一个可用计划（永不返回 None）。

调度器只产出「路由计划」，不直接入库、不直接调专项能力——执行由端点层按计划推进。
对应 docs/deepcoffee-ai-prompts.md §1。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.prompts import COFFEA_DISPATCH_SYSTEM, COFFEA_DISPATCH_USER_TEMPLATE
from app.schemas.coffea import DispatchPlan
from app.services.model_gateway import ModelGateway, is_insufficient_quota, model_gateway
from app.services.model_json import ModelJSONError, chat_json

logger = logging.getLogger(__name__)

# 允许的 primary_intent / action.type（与 §1 提示词、§1 词表约定逐字对应）。
ALLOWED_INTENTS: tuple[str, ...] = (
    "read_bean_card_image",
    "assess_brew_photo",
    "create_or_update_bean_card",
    "recommend_brew_params",
    "adjust_brew_params",
    "scale_recipe",
    "grinder_conversion",
    "brew_record_parse",
    "knowledge_answer",
    "web_verify",
    "equipment_advice",
    "storage_resting_advice",
    "direct_answer",
    "ask_clarification",
    "out_of_scope",
)
# 只作意图、没有对应专项能力（调度器直接处理）。
INTENT_ONLY: frozenset[str] = frozenset({"direct_answer", "ask_clarification", "out_of_scope"})

# 调度器 JSON 的合法顶层键（多余键丢弃，缺主意图即回退）。
PLAN_KEYS: list[str] = [
    "primary_intent",
    "secondary_intents",
    "actions",
    "state_updates",
    "direct_reply",
    "should_answer_directly",
]

# 本地兜底用的关键词表（粗粒度，仅在模型不可用时启用）。
_PHOTO_BREW_HINTS = ("冲完", "粉床", "萃取", "液面", "流速", "通道", "偏酸", "偏苦", "调参")
# 注意：这组词只在「带附件」分支用，宽一点没关系——带图说「记录/这只豆子」就是想读卡建档
_BEAN_CARD_HINTS = ("豆卡", "豆袋", "包装", "标签", "卡片", "ocr", "文字", "产地", "处理法", "豆子", "记录", "建档", "录入", "这支豆", "这只豆")
_WEB_HINTS = ("网上", "评论", "最新", "核实", "口碑", "官方说", "有人说", "真的吗")
_PARAM_HINTS = ("方案", "参数", "怎么冲", "冲煮建议", "配方", "几克", "粉水比", "水温", "recommend")
_KNOWLEDGE_HINTS = ("？", "?", "什么", "为什么", "怎么", "如何", "区别", "吗", "科普")


def _as_text(value: Any) -> str:
    """把上下文片段转成可放进提示词的紧凑文本；空值给「（无）」。"""
    if value is None or value == "" or value == [] or value == {}:
        return "（无）"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _attachments_brief(attachments: Any) -> list[dict[str, Any]] | None:
    """附件只给元信息（ref/类型/大小），**绝不把 base64 原文塞进调度提示词**。

    一张图的 data URL 就是百万级 token：new-api 预扣费按输入长度估算，直接
    insufficient_user_quota，整条模型路径塌成本地关键词兜底（用户表述了需求
    仍被反问）。调度只需要知道「有什么附件」，图片本体由专项能力经 vision 通道读。
    """
    if not attachments:
        return None
    items = attachments if isinstance(attachments, list) else [attachments]
    brief: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, dict):
            data = item.get("data_url")
            brief.append({
                "ref": f"attachment_{index}",
                "type": item.get("type") or "image",
                "mime_type": item.get("mime_type"),
                "approx_kb": round(len(data) * 3 / 4 / 1024) if isinstance(data, str) else None,
            })
        else:
            brief.append({"ref": f"attachment_{index}", "type": "unknown"})
    return brief


async def dispatch_with_model(
    *,
    message: str,
    attachments: Any = None,
    session_state: dict | None = None,
    recent_beans: Any = None,
    recent_brews: Any = None,
    equipment_profiles: Any = None,
    taste_preferences: Any = None,
    token: str | None,
    model: str,
    gateway: ModelGateway | None = None,
    failure_reasons: list[str] | None = None,
) -> DispatchPlan | None:
    """模型路径。成功返回校验过的计划；任何条件不满足 / 不合规返回 None（调用方回退本地）。

    failure_reasons：可选收集器。失败原因可分类时（如余额耗尽）追加标签，
    供 dispatch() 写进兜底计划的 degrade_reason。
    """
    gw = gateway or model_gateway
    if not token or not gw.enabled:
        return None
    user_content = COFFEA_DISPATCH_USER_TEMPLATE.format(
        session_state=_as_text(session_state),
        recent_beans=_as_text(recent_beans),
        recent_brews=_as_text(recent_brews),
        equipment_profiles=_as_text(equipment_profiles),
        taste_preferences=_as_text(taste_preferences),
        message=message,
        attachments=_as_text(_attachments_brief(attachments)),
    )
    messages = [
        {"role": "system", "content": COFFEA_DISPATCH_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    try:
        data = await chat_json(
            gw,
            user_token=token,
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=900,
            required_keys=["primary_intent"],
            allowed_keys=PLAN_KEYS,
        )
    except ModelJSONError as exc:
        logger.warning("coffea_dispatch model JSON invalid, fallback to local: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 — 模型/网关失败即回退本地，绝不打断对话
        if is_insufficient_quota(exc):
            # 余额耗尽要喊出来：ERROR 级日志 + 标签上抛，响应层会在 reply 里提示用户
            logger.error("coffea_dispatch blocked by exhausted new-api balance: %s", exc)
            if failure_reasons is not None:
                failure_reasons.append("balance_exhausted")
        else:
            logger.warning("coffea_dispatch model call failed, fallback to local: %s", exc)
        return None

    intent = data.get("primary_intent")
    if intent not in ALLOWED_INTENTS:
        logger.warning("coffea_dispatch returned unknown intent %r, fallback to local", intent)
        return None

    secondary = [s for s in (data.get("secondary_intents") or []) if isinstance(s, str)]
    actions = [a for a in (data.get("actions") or []) if isinstance(a, dict)]
    state_updates = data.get("state_updates")
    if not isinstance(state_updates, dict):
        state_updates = {}
    direct_reply = data.get("direct_reply")
    if direct_reply is not None and not isinstance(direct_reply, str):
        direct_reply = None
    return DispatchPlan(
        primary_intent=intent,
        secondary_intents=secondary,
        actions=actions,
        state_updates=state_updates,
        direct_reply=direct_reply,
        should_answer_directly=bool(data.get("should_answer_directly")),
        source="model",
    )


def local_dispatch(
    *,
    message: str,
    attachments: Any = None,
    session_state: dict | None = None,
) -> DispatchPlan:
    """本地启发式兜底（§1「降级」）：文字决定主角色，图片只作为本轮附件随角色传入；
    有 active 豆且问方案走建议，联网/知识关键词分流，都判断不了就追问。永远返回一个可用计划。"""
    text = message or ""
    low = text.lower()
    state = session_state or {}
    has_attachment = bool(attachments)

    if any(k in low for k in _WEB_HINTS):
        return DispatchPlan(
            primary_intent="web_verify",
            actions=[{"type": "web_verify"}],
            source="local",
        )

    if any(k in text for k in _PHOTO_BREW_HINTS):
        return DispatchPlan(
            primary_intent="adjust_brew_params",
            actions=[{"type": "adjust_brew_params"}],
            source="local",
        )

    if has_attachment and any(k in low or k in text for k in _BEAN_CARD_HINTS):
        return DispatchPlan(
            primary_intent="read_bean_card_image",
            actions=[{"type": "read_bean_card_image", "input_ref": "attachment_1"}],
            source="local",
        )

    if state.get("active_bean_id") and any(k in low for k in _PARAM_HINTS):
        return DispatchPlan(
            primary_intent="recommend_brew_params",
            actions=[{"type": "recommend_brew_params"}],
            source="local",
        )

    if any(k in text for k in _KNOWLEDGE_HINTS):
        return DispatchPlan(
            primary_intent="knowledge_answer",
            actions=[{"type": "knowledge_answer"}],
            source="local",
        )

    if has_attachment:
        return DispatchPlan(
            primary_intent="ask_clarification",
            actions=[],
            direct_reply="我收到了图片。你想让我读豆卡 / 包装文字、看冲煮状态，还是结合图片回答一个问题？",
            source="local",
        )

    return DispatchPlan(
        primary_intent="ask_clarification",
        actions=[],
        direct_reply="可以多说一点吗？比如你想了解某支豆子、要一份冲煮方案，还是记录一杯冲煮。",
        source="local",
    )


async def dispatch(
    *,
    message: str,
    attachments: Any = None,
    session_state: dict | None = None,
    recent_beans: Any = None,
    recent_brews: Any = None,
    equipment_profiles: Any = None,
    taste_preferences: Any = None,
    token: str | None = None,
    model: str,
    gateway: ModelGateway | None = None,
) -> DispatchPlan:
    """对外入口：先试模型，失败即本地兜底。返回的计划必带 source 标注。"""
    failure_reasons: list[str] = []
    plan = await dispatch_with_model(
        message=message,
        attachments=attachments,
        session_state=session_state,
        recent_beans=recent_beans,
        recent_brews=recent_brews,
        equipment_profiles=equipment_profiles,
        taste_preferences=taste_preferences,
        token=token,
        model=model,
        gateway=gateway,
        failure_reasons=failure_reasons,
    )
    if plan is not None:
        return plan
    fallback = local_dispatch(message=message, attachments=attachments, session_state=session_state)
    if "balance_exhausted" in failure_reasons:
        fallback.degrade_reason = "balance_exhausted"
    return fallback
