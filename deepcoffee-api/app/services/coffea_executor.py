"""按调度器的路由计划执行动作（Phase 2 收尾）。

调度器只产「计划」；这里把计划里能现在执行的动作真正跑起来，产出 `ActionResult`：
- `knowledge_answer`：复用已上线知识库问答；本轮原始图片会随问题进入该能力。
- `read_bean_card_image` / `assess_brew_photo`：用户明确要求读图时，试 image_understanding。
- `brew_coach` / `web_verify`：接收本轮原始附件，由角色自己判断图片是否有用。
- 写库类动作（豆卡/冲煮/建议）：标 `pending`，进入确认流程后再写库。

每个能力内部都「有就用、没有就降级/兜底」，绝不让单个动作失败打断整轮对话。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.config import Settings
from app.schemas.brew import BrewDraft
from app.schemas.coffea import ActionResult, DispatchPlan
from app.services import bean_card_intake
from app.services.ai_answer import answer_with_model
from app.services.brew_coach import LOCAL_COACH_FALLBACK, coach_with_model
from app.services.brew_parse_ai import parse_brew_with_model
from app.services.image_understanding import understand_image
from app.services.input_parser import assess_brew_draft, parse_brew_input
from app.services.knowledge_service import KnowledgeService
from app.services.multimodal import image_data_urls
from app.services.model_gateway import ModelGateway
from app.services import web_search, web_verify

logger = logging.getLogger(__name__)

_IMAGE_ACTIONS = frozenset({"read_bean_card_image", "assess_brew_photo"})
# 这些动作交给冲煮教练 brew_coach（§8）。
_COACH_ACTIONS = frozenset(
    {"adjust_brew_params", "scale_recipe", "grinder_conversion", "storage_resting_advice", "equipment_advice"}
)
# 仅作意图、无执行动作（由调度器的 direct_reply 直接回用户）。
# 注意：direct_answer 不在此列——它要真正调模型生成回答（见 execute_plan），否则回答全靠
# 调度器顺手填的 direct_reply，常为空导致空回复。
_INTENT_ONLY = frozenset({"ask_clarification", "out_of_scope"})
_DISPLAYABLE_RESULT_STATUSES = frozenset({"done", "degraded"})
# 会产出「正文型」综合回答、可合并进主回复的动作（区别于豆卡/草稿/图片那类状态型消息）。
# 一轮可能有多条（如 knowledge_answer 答一部分 + web_verify 补一部分），全部并进主回复，
# 这样卡片只剩来源链接、内容不被埋进卡片也不丢失。
_ANSWER_TYPES = frozenset({
    "knowledge_answer",
    "web_verify",
    "direct_answer",
    "adjust_brew_params",
    "scale_recipe",
    "grinder_conversion",
    "storage_resting_advice",
    "equipment_advice",
})
# 写库类动作（建/改豆卡、生成建议参数）故意不在聊天单轮自动执行，避免一句话误改用户数据。
# 给明确的引导语，指向各自的确认流程，而不是笼统的「后续阶段接入」（那会被前端误显示成"处理中"）。
# brew_record_parse 例外：消息里带参数时真解析出草稿（落库仍由用户在草稿卡确认）。
_PENDING_GUIDANCE = {
    "brew_record_parse": "想记录这杯吗？把冲煮参数发我（豆子、粉量、水量、水温、时间、风味），或到「记录冲煮」页录入——记录会在你确认后才入库。",
    "create_or_update_bean_card": "想建立或修改这支豆子的豆卡吗？到「豆仓」新建 / 编辑，确认后才保存。",
    "recommend_brew_params": "想要冲煮建议参数吗？在对应豆子的「生成建议参数」发起，会先问你的器具再给方案。",
}
# 冲煮草稿关键字段 → 中文名（缺失提示用）。与 input_parser.assess_brew_draft 的字段集一致。
_BREW_FIELD_LABELS = {
    "bean_name": "豆子",
    "device": "滤杯",
    "dose_g": "粉量",
    "water_ml": "水量",
    "water_temp_c": "水温",
    "grinder": "磨豆机",
    "grind_setting": "研磨刻度",
    "brew_time_seconds": "冲煮时间",
}
_EQUIPMENT_CATEGORY_LABELS = {
    "brewer": "冲煮器具",
    "grinder": "磨豆机",
    "filter_media": "过滤介质",
    "water": "用水",
}
_BREW_METHOD_HINTS = (
    ("法压", "法压壶"),
    ("french", "法压壶"),
    ("爱乐压", "爱乐压"),
    ("aeropress", "爱乐压"),
    ("聪明杯", "浸泡式"),
    ("clever", "浸泡式"),
    ("浸泡", "浸泡式"),
    ("espresso", "意式"),
    ("意式", "意式"),
    ("摩卡", "摩卡壶"),
    ("moka", "摩卡壶"),
    ("冷萃", "冷萃"),
    ("手冲", "滤杯冲煮"),
    ("滤杯", "滤杯冲煮"),
    ("v60", "滤杯冲煮"),
)
_BREWER_PATTERNS = (
    (r"\bV60(?:\s*0?[123])?\b", "V60"),
    (r"Origami|折纸", "Origami"),
    (r"Kalita", "Kalita"),
    (r"Chemex", "Chemex"),
    (r"法压壶|法压|French\s*Press", "法压壶"),
    (r"爱乐压|AeroPress", "爱乐压"),
    (r"聪明杯|Clever", "聪明杯"),
)
_GRINDER_PATTERNS = (
    (r"ZP6S?|1zpresso\s*ZP6S?", "ZP6S"),
    (r"Comandante\s*C40|C40|司令官", "Comandante C40"),
    (r"EK43", "EK43"),
    (r"K-Ultra", "K-Ultra"),
    (r"泰摩|Timemore", "Timemore"),
)
_FILTER_PATTERNS = (
    (r"V60\s*滤纸|锥形滤纸|滤纸|纸滤", "纸滤"),
    (r"金属滤网|金属滤纸", "金属滤网"),
    (r"法压.*滤网|内置滤网", "内置滤网"),
)
_WATER_PATTERNS = (
    (r"农夫山泉", "农夫山泉"),
    (r"怡宝", "怡宝"),
    (r"屈臣氏", "屈臣氏"),
    (r"自配水|自制水", "自配水"),
    (r"矿泉水", "矿泉水"),
)
_EQUIPMENT_CAPTURE_HINTS = (
    "我买了",
    "我用了",
    "我用",
    "我的",
    "新买",
    "存",
    "保存",
    "录入",
    "记录器具",
    "要存",
)
_PENDING_FALLBACK = "这一步要走专门的确认流程，避免在聊天里直接改动你的数据。"
# 暂无联网检索能力，web_verify 降级时的显式标注（§9 降级）。
_WEB_VERIFY_DISCLAIMER = "（暂不能联网实时核实，以下基于本地知识库与一般经验，不代表最新网络信息）"
# 图片理解整体不可用（vision 未配 / 无 token / 调用失败）时的兜底引导。
_IMAGE_UNAVAILABLE_GUIDANCE = "我没能识别这张图片。可以把卡片或包装上的文字直接发给我，或到「我的豆仓」手动录入。"


async def execute_plan(
    plan: DispatchPlan,
    *,
    message: str,
    attachments: list[dict[str, Any]] | None,
    session_state: dict | None,
    knowledge_service: KnowledgeService,
    settings: Settings,
    model: str,
    active_context: dict | None = None,
    history: list[dict[str, str]] | None = None,
    gateway: ModelGateway | None = None,
) -> list[ActionResult]:
    results: list[ActionResult] = []
    current_image_urls = image_data_urls(attachments)
    # direct_answer（不需专项工具的普通咖啡问答）也要真正生成回答：调度器只给意图、没给 action 时
    # 这里补一个，避免回答全靠（常为空的）direct_reply 而出现空回复。
    actions = list(plan.actions)
    if plan.primary_intent == "direct_answer" and not any(
        isinstance(a, dict) and a.get("type") == "direct_answer" for a in actions
    ):
        actions.append({"type": "direct_answer"})
    for action in actions:
        action_type = action.get("type") if isinstance(action, dict) else None
        if not action_type:
            continue
        try:
            if action_type == "knowledge_answer":
                results.append(
                    await _run_knowledge(
                        message,
                        image_urls=current_image_urls,
                        knowledge_service=knowledge_service,
                        settings=settings,
                        model=model,
                        history=history,
                        gateway=gateway,
                    )
                )
            elif action_type in _IMAGE_ACTIONS:
                results.append(
                    await _run_image(
                        action_type,
                        message=message,
                        attachments=attachments,
                        session_state=session_state,
                        settings=settings,
                        gateway=gateway,
                    )
                )
            elif action_type in _COACH_ACTIONS:
                results.append(
                    await _run_coach(
                        action_type,
                        message=message,
                        active_context=active_context,
                        session_state=session_state,
                        image_urls=current_image_urls,
                        settings=settings,
                        model=model,
                        history=history,
                        gateway=gateway,
                    )
                )
            elif action_type == "web_verify":
                results.append(
                    await _run_web_verify(
                        message,
                        attachments=attachments,
                        image_urls=current_image_urls,
                        session_state=session_state,
                        knowledge_service=knowledge_service,
                        settings=settings,
                        model=model,
                        history=history,
                        gateway=gateway,
                    )
                )
            elif action_type == "brew_record_parse":
                results.append(
                    await _run_brew_parse(
                        message,
                        model=model,
                        gateway=gateway,
                        history=history,
                        active_recipe=(active_context or {}).get("recipe"),
                    )
                )
            elif action_type == "equipment_capture":
                results.append(
                    await _run_equipment_capture(
                        message,
                        model=model,
                        gateway=gateway,
                        history=history,
                        active_context=active_context,
                    )
                )
            elif action_type == "direct_answer":
                # 不需专项工具的普通咖啡问答：用冲煮教练（自由文本，带历史/画像/活跃上下文）真正生成回答。
                results.append(
                    await _run_coach(
                        "direct_answer",
                        message=message,
                        active_context=active_context,
                        session_state=session_state,
                        image_urls=current_image_urls,
                        settings=settings,
                        model=model,
                        history=history,
                        gateway=gateway,
                    )
                )
            elif action_type in _INTENT_ONLY:
                # 调度器已经把要直接说的话放在 direct_reply，这里不重复产出动作结果。
                continue
            else:
                results.append(
                    ActionResult(
                        type=action_type,
                        status="pending",
                        message=_PENDING_GUIDANCE.get(action_type, _PENDING_FALLBACK),
                    )
                )
        except Exception as exc:  # noqa: BLE001 — 单动作失败不打断整轮；保留已完成结果
            logger.warning("coffea action %r failed: %s", action_type, exc)
            results.append(ActionResult(type=action_type, status="failed", message="这一步暂时没能完成。"))
    return results


def assemble_reply(plan: DispatchPlan, results: list[ActionResult]) -> str | None:
    """组装本轮最终主回复。

    direct_reply 只表示调度器自己可直接说的话；知识问答、联网核实、冲煮教练等动作执行后，
    results[].message 才是带上下文 / 来源 / 降级标注的答案，所以非 intent-only 场景优先展示执行结果。

    多个正文型回答合并进主回复（主意图在前），让卡片只剩来源链接、内容不被埋进卡片或丢失。
    教练兜底空话（LOCAL_COACH_FALLBACK）视为「非实质」：本轮另有实质回答时不让它顶掉真答案——
    兜住「调度器误把问答型请求又附带教练动作、教练无话可说只回兜底」的情况。
    """
    if plan.primary_intent in _INTENT_ONLY:
        return plan.direct_reply

    def _substantive(message: str | None) -> bool:
        return bool(message) and message.strip() != LOCAL_COACH_FALLBACK.strip()

    displayable = [r for r in results if r.status in _DISPLAYABLE_RESULT_STATUSES and r.message]

    # 状态型主回复（豆卡识别摘要 / 冲煮草稿 / 图片评估）自成主回复，不被正文型综合顶替。
    primary = next((r for r in displayable if r.type == plan.primary_intent), None)
    if primary is not None and primary.type not in _ANSWER_TYPES and _substantive(primary.message):
        return primary.message

    # 正文型实质回答全部合并（主意图在前、去重），即「一轮多个答案」的合并落点。
    answers = sorted(
        (r for r in displayable if r.type in _ANSWER_TYPES and _substantive(r.message)),
        key=lambda r: 0 if r.type == plan.primary_intent else 1,
    )
    combined: list[str] = []
    for r in answers:
        msg = r.message.strip()
        if msg not in combined:
            combined.append(msg)
    if combined:
        return "\n\n".join(combined)

    # 兜底：全无实质正文（仅教练兜底空话 / 仅状态型）→ 主意图结果 / 任一结果 / direct_reply。
    primary_any = primary.message if primary else None
    return primary_any or (displayable[0].message if displayable else None) or plan.direct_reply


async def _run_knowledge(
    message: str,
    *,
    image_urls: list[str] | None,
    history: list[dict[str, str]] | None = None,
    knowledge_service: KnowledgeService,
    settings: Settings,
    model: str,
    gateway: ModelGateway | None,
) -> ActionResult:
    kb = knowledge_service.answer_question(message)
    answer = kb.answer
    source = "local"
    if kb.from_knowledge_base or image_urls:
        grounding = (
            knowledge_service.build_grounding([f.slug for f in kb.selected_files], settings)
            if kb.from_knowledge_base
            else []
        )
        model_answer = await answer_with_model(
            message,
            grounding,
            model=model,
            image_urls=image_urls,
            history=history,
            vision_model=settings.vision_model,
            gateway=gateway,
        )
        if model_answer:
            answer = model_answer
            source = "model"
    return ActionResult(
        type="knowledge_answer",
        status="done",
        source=source,
        output={
            "answer": answer,
            "from_knowledge_base": kb.from_knowledge_base,
            "sources": [s.model_dump() for s in kb.sources],
        },
        message=answer,
    )


async def _run_image(
    action_type: str,
    *,
    message: str,
    attachments: list[dict[str, Any]] | None,
    session_state: dict | None,
    settings: Settings,
    gateway: ModelGateway | None,
) -> ActionResult:
    data = await understand_image(
        message=message,
        images=image_data_urls(attachments),
        session_state=session_state,
        vision_model=settings.vision_model,
        gateway=gateway,
    )
    if data is None:
        return ActionResult(
            type=action_type,
            status="degraded",
            source="local",
            message=_IMAGE_UNAVAILABLE_GUIDANCE,
        )
    if action_type == "read_bean_card_image":
        return _bean_card_result(data, settings)
    return ActionResult(
        type=action_type,
        status="done",
        source="model",
        output=data,
        message=_brew_photo_summary(data),
    )


def _bean_card_result(data: dict[str, Any], settings: Settings) -> ActionResult:
    """豆卡识图：原始 JSON 不给用户看，转成草稿 + 综合识别度 + 人话摘要。

    auto_save_eligible 只是执行器的判定；真正落库由端点层做（执行器保持无副作用）。
    """
    if data.get("image_type") != "bean_card":
        return ActionResult(
            type="read_bean_card_image",
            status="degraded",
            source="model",
            message="这张图看起来不像豆卡。换一张清晰的豆卡照片，或把卡片上的文字发给我，也可以到「我的豆仓」手动录入。",
        )
    draft = bean_card_intake.draft_from_bean_fields(data)
    confidence = bean_card_intake.effective_confidence(data, draft)
    summary = bean_card_intake.summarize_draft(draft)
    if not (draft.name or draft.roaster_product_name):
        return ActionResult(
            type="read_bean_card_image",
            status="degraded",
            source="model",
            message=f"我从图片里识别到：{summary}，但没读出豆名。可以把豆卡文字发给我，或到「我的豆仓」手动录入。",
        )
    uncertainties = [u for u in (data.get("uncertainties") or []) if isinstance(u, str) and u.strip()]
    uncertain_note = f"其中「{'、'.join(uncertainties[:3])}」不太确定，" if uncertainties else ""
    return ActionResult(
        type="read_bean_card_image",
        status="done",
        source="model",
        output={
            "draft": draft.model_dump(exclude_none=True),
            "confidence": confidence,
            "uncertainties": uncertainties,
            "auto_save_eligible": confidence >= settings.bean_card_autosave_confidence,
            "raw_input": bean_card_intake.ocr_raw_input(data),
        },
        message=f"我从图片里识别到：{summary}。{uncertain_note}请在下面的草稿卡里确认或修改后保存。",
    )


def _brew_photo_summary(data: dict[str, Any]) -> str | None:
    """冲煮照片评估：从结构化输出里挑可读结论，避免裸 JSON 卡片。"""
    assessment = data.get("brew_photo_assessment")
    if not isinstance(assessment, dict):
        return None
    facts = [s for s in (assessment.get("observed_facts") or []) if isinstance(s, str) and s.strip()]
    suggestions = [s for s in (assessment.get("suggested_adjustments") or []) if isinstance(s, str) and s.strip()]
    parts: list[str] = []
    if facts:
        parts.append("从照片里看到：" + "；".join(facts[:3]) + "。")
    if suggestions:
        parts.append("建议：" + "；".join(suggestions[:3]) + "。")
    return " ".join(parts) or None


def _brew_summary(draft: BrewDraft) -> str:
    """已解析字段的一句人话摘要（只列识别到的）。"""
    parts: list[str] = []
    if draft.bean_name:
        parts.append(draft.bean_name)
    if draft.brew_method:
        parts.append(draft.brew_method)
    if draft.device:
        parts.append(draft.device)
    grind = f"{draft.grinder or ''} {draft.grind_setting or ''}".strip()
    if grind:
        parts.append(grind)
    if draft.filter_media:
        parts.append(draft.filter_media)
    if draft.water:
        parts.append(draft.water)
    if draft.dose_g:
        parts.append(f"粉 {draft.dose_g:g}g")
    if draft.water_ml:
        parts.append(f"水 {draft.water_ml:g}ml")
    if draft.water_temp_c:
        parts.append(f"{draft.water_temp_c:g}°C")
    if draft.ratio:
        parts.append(f"粉水比 {draft.ratio}")
    if draft.brew_time_seconds:
        parts.append(f"{draft.brew_time_seconds // 60}:{draft.brew_time_seconds % 60:02d}")
    if draft.brew_steps:
        parts.append(f"{len(draft.brew_steps)} 段注水")
    return " · ".join(parts)


def _history_excerpt(history: list[dict[str, str]] | None, *, limit: int = 6) -> str:
    lines: list[str] = []
    for item in (history or [])[-limit:]:
        role = item.get("role") or "user"
        content = (item.get("content") or item.get("text") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _contextual_brew_text(
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
    active_recipe: dict[str, Any] | None = None,
) -> str:
    parts: list[str] = []
    history_text = _history_excerpt(history)
    if history_text:
        parts.append(f"最近对话：\n{history_text}")
    if active_recipe:
        parts.append(f"当前活跃冲煮方案：\n{active_recipe}")
    parts.append(f"本轮用户消息：\n{message}")
    return "\n\n".join(parts)


def _has_brew_substance(draft: BrewDraft) -> bool:
    return any([
        draft.brew_method, draft.device, draft.grinder, draft.grind_setting, draft.filter_media, draft.water,
        draft.dose_g, draft.water_ml, draft.water_temp_c, draft.ratio, draft.brew_time_seconds, draft.brew_steps,
    ])


async def _run_brew_parse(
    message: str,
    *,
    model: str,
    gateway: ModelGateway | None,
    history: list[dict[str, str]] | None = None,
    active_recipe: dict[str, Any] | None = None,
) -> ActionResult:
    """聊天里记录冲煮：消息带参数就真解析成草稿（缺什么明确说），落库由用户在草稿卡确认。

    完全没解析出参数（纯意图，如「我想记录冲煮」）才回通用引导语。
    """
    parse_text = _contextual_brew_text(message, history=history, active_recipe=active_recipe)
    draft = await parse_brew_with_model(parse_text, model=model, gateway=gateway)
    source = "model"
    if draft is None:
        draft, _, _, _ = parse_brew_input(parse_text)
        source = "local"
    _enrich_brew_draft_from_text(draft, parse_text)
    confidence, missing, _ = assess_brew_draft(draft)
    # 「实质参数」不含 bean_name：本地启发式几乎任何句子都能抽出个"豆名"，
    # 纯意图消息（"我想记录冲煮"）必须仍走通用引导，而不是抱着垃圾豆名出草稿。
    if not _has_brew_substance(draft):
        return ActionResult(
            type="brew_record_parse",
            status="pending",
            source=source,
            message=_PENDING_GUIDANCE["brew_record_parse"],
        )
    summary = _brew_summary(draft)
    missing_labels = [_BREW_FIELD_LABELS[f] for f in missing if f in _BREW_FIELD_LABELS]
    if missing_labels:
        msg = (
            f"我从你的描述里解析出：{summary}。"
            f"还缺{('、'.join(missing_labels[:4]))}，可以直接在下面的草稿卡里补充，确认后保存。"
        )
    else:
        msg = f"我从你的描述里解析出：{summary}。信息齐了，请在下面的草稿卡确认保存。"
    return ActionResult(
        type="brew_record_parse",
        status="done",
        source=source,
        output={
            "draft": draft.model_dump(exclude_none=True),
            "confidence": confidence,
            "missing_fields": missing,
            "raw_input": message,
        },
        message=msg,
    )


# 明显在说豆卡/豆子的措辞：此时「记录」指录豆卡，不是记冲煮。
_BEAN_CARD_PHRASES = ("豆卡", "这支豆", "这包豆", "这袋豆", "豆袋", "这只豆", "录入豆")
# 明确的冲煮词：句中即便提到豆子，带这些仍按冲煮记录意图处理。
_BREW_WORDS = ("冲煮", "这杯", "冲了", "萃取", "这一杯", "冲这")


def _contains_brew_record_hint(message: str) -> bool:
    """用户是否明确表达「想记录这杯冲煮」。覆盖自然说法（我要记录一次冲煮 / 想记录下来 等）。

    但当消息明显在说豆卡/豆子（如「帮我记录这个豆卡」）且无冲煮词时，「记录」指录豆卡、不算冲煮意图。
    """
    has_hint = any(
        hint in message
        for hint in (
            "记录这杯", "记录这次", "记录冲煮", "记录一杯", "记录一次", "记录今天",
            "帮我记录", "想记录", "记录一下", "记一下", "保存这杯", "存这杯",
        )
    )
    if not has_hint:
        return False
    if any(p in message for p in _BEAN_CARD_PHRASES) and not any(w in message for w in _BREW_WORDS):
        return False
    return True


# 「冲煮量」信号：粉量/水量/水温/时间/粉水比/分段——这些只有真在描述一杯冲煮时才会出现。
# 故意不含「刻度」与「磨豆机名+数字」：那是研磨刻度换算（grinder_conversion）的问句，不是冲煮记录。
# 水温「92度」需数字紧贴「度」，从而排除「刻度」（刻+度，度前无数字）。
_BREW_QUANTITY_RE = re.compile(
    r"\d+\s*(?:g|克|ml|毫升|°c|℃|秒|分钟)"
    r"|\d+\s*度"
    r"|粉水比|水粉比"
    r"|1\s*[:：]\s*\d+"
    r"|闷蒸|分段注水",
    re.IGNORECASE,
)
# 冲煮记录的「核心量化字段」：判定一段话算不算冲煮详情，看这些凑没凑够（≥2）。
# 磨豆机/刻度/器具不在其列——只报器具或刻度不构成一条冲煮记录。
_CORE_BREW_FIELDS = ("dose_g", "water_ml", "water_temp_c", "brew_time_seconds")


def _mentions_brew_quantity(text: str) -> bool:
    """便宜的前置过滤：文本里有没有真正的冲煮量（粉/水/温/时/比/分段）。无则不必调模型解析。"""
    return bool(_BREW_QUANTITY_RE.search(text or ""))


def _draft_substance_count(draft: dict[str, Any]) -> int:
    """草稿里凑齐了几个冲煮记录核心字段（粉量/水量/水温/时间/粉水比/分段）。"""
    count = sum(1 for field in _CORE_BREW_FIELDS if draft.get(field) is not None)
    if draft.get("ratio_value") is not None or draft.get("ratio"):
        count += 1
    if draft.get("brew_steps"):
        count += 1
    return count


def _official_recipe_from_bean(bean: dict[str, Any] | None) -> str | None:
    """从活跃豆卡的备注里抽出「官方建议：…」那行（豆袋上的推荐配方），用于预填冲煮草稿。"""
    if not bean:
        return None
    notes = bean.get("private_notes") or ""
    for raw in notes.splitlines():
        line = raw.strip()
        for prefix in ("官方建议：", "官方建议:"):
            if line.startswith(prefix):
                rest = line[len(prefix):].strip()
                return rest or None
    return None


async def _brew_draft_for_bean(
    message: str,
    *,
    active_bean: dict[str, Any],
    model: str,
    gateway: ModelGateway | None,
    history: list[dict[str, str]] | None,
    active_recipe: dict[str, Any] | None,
) -> ActionResult:
    """为活跃豆卡生成一张冲煮草稿：关联该豆，并按豆袋官方配方（若有）预填粉量/水量/水温等。

    用于「追问体系」确认轮（用户点「记录一次冲煮」）：即便消息没参数也给草稿卡，豆袋无配方则留空。
    """
    parse_text = _contextual_brew_text(message, history=history, active_recipe=active_recipe)
    official = _official_recipe_from_bean(active_bean)
    if official:
        parse_text = f"{parse_text}\n{official}".strip()
    draft = await parse_brew_with_model(parse_text, model=model, gateway=gateway)
    source = "model"
    if draft is None:
        draft, _, _, _ = parse_brew_input(parse_text)
        source = "local"
    _enrich_brew_draft_from_text(draft, parse_text)
    # 关联刚记录/活跃的豆子（本地解析可能抽出垃圾豆名，直接以活跃豆名覆盖）。
    bean_name = active_bean.get("name")
    if bean_name:
        draft.bean_name = bean_name
    confidence, missing, _ = assess_brew_draft(draft)
    summary = _brew_summary(draft)
    missing_labels = [_BREW_FIELD_LABELS[f] for f in missing if f in _BREW_FIELD_LABELS]
    if official:
        msg = f"好的，给「{bean_name or '这支豆子'}」建一张冲煮草稿，已带上豆袋的推荐参数：{summary}。"
    else:
        msg = f"好的，给「{bean_name or '这支豆子'}」建一张冲煮草稿。"
    if missing_labels:
        msg += f"还缺{('、'.join(missing_labels[:4]))}，在下面补全后确认保存。"
    else:
        msg += "确认后保存。"
    return ActionResult(
        type="brew_record_parse",
        status="done",
        source=source,
        output={
            "draft": draft.model_dump(exclude_none=True),
            "confidence": confidence,
            "missing_fields": missing,
            "raw_input": message,
        },
        message=msg,
    )


async def ensure_brew_draft_result(
    results: list[ActionResult],
    *,
    message: str,
    model: str,
    gateway: ModelGateway | None = None,
    history: list[dict[str, str]] | None = None,
    active_recipe: dict[str, Any] | None = None,
    active_bean: dict[str, Any] | None = None,
) -> None:
    """端点级兜底：调度没附 brew_record_parse 时，仍可主动补冲煮草稿。

    判定依据 = 冲煮记录的「必要元素」，而不是宽泛的「像有参数」：
      ① 用户明确说要记录（记录这杯 / 想记录…）；或
      ② 用户确实报了冲煮详情——解析出的草稿凑齐「足量核心字段」（粉量/水量/水温/时间/
         粉水比/分段 中 ≥2 项）。仅出现磨豆机+刻度（如「C40 刻度 22 对应 ZP6s」）不算。
    明确要记录且有活跃豆卡时（追问体系确认轮），草稿关联该豆并按豆袋官方配方预填。
    """
    has_brew_result = any(r.type == "brew_record_parse" for r in results)
    if any(r.type == "brew_record_parse" and isinstance(r.output, dict) and r.output.get("draft") for r in results):
        return
    explicit = _contains_brew_record_hint(message)
    if not explicit:
        # 没说要记录：先看这句话里有没有真正的冲煮量，没有就连模型都不必调。
        parse_text = _contextual_brew_text(message, history=history, active_recipe=active_recipe)
        if not _mentions_brew_quantity(parse_text):
            return
    if explicit and active_bean:
        # 明确要记录 + 有活跃豆：直接为该豆建草稿（关联豆 + 豆袋配方预填），即便消息没参数也给卡。
        results.append(
            await _brew_draft_for_bean(
                message,
                active_bean=active_bean,
                model=model,
                gateway=gateway,
                history=history,
                active_recipe=active_recipe,
            )
        )
        return
    candidate = await _run_brew_parse(
        message,
        model=model,
        gateway=gateway,
        history=history,
        active_recipe=active_recipe,
    )
    if explicit:
        # 明确要记录：即便信息少也给草稿卡，引导补全。
        if candidate.status == "done" or not has_brew_result:
            results.append(candidate)
        return
    # 没明确说记录：只有解析出「足量核心字段」才主动展示草稿，避免给刻度换算/器具问句硬塞草稿。
    if candidate.status != "done" or not isinstance(candidate.output, dict):
        return
    draft = candidate.output.get("draft") or {}
    if _draft_substance_count(draft) >= 2:
        results.append(candidate)


def _first_pattern(text: str, patterns: tuple[tuple[str, str], ...]) -> str | None:
    for pattern, value in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            raw = match.group(0).strip()
            return raw if value in {"V60"} and raw.upper().startswith("V60") else value
    return None


def _brew_method_from_text(text: str) -> str | None:
    low = text.lower()
    for needle, method in _BREW_METHOD_HINTS:
        if needle in low or needle in text:
            return method
    return None


def _enrich_brew_draft_from_text(draft: BrewDraft, text: str) -> None:
    if not draft.brew_method:
        draft.brew_method = _brew_method_from_text(text)
    if not draft.device:
        draft.device = _first_pattern(text, _BREWER_PATTERNS)
    grinder = _first_pattern(text, _GRINDER_PATTERNS)
    if grinder and (not draft.grinder or (draft.grinder.strip().lower() == "zp6" and grinder == "ZP6S")):
        draft.grinder = grinder
    if not draft.filter_media:
        draft.filter_media = _first_pattern(text, _FILTER_PATTERNS)
    if not draft.water:
        draft.water = _first_pattern(text, _WATER_PATTERNS)


def _equipment_items_from_draft(draft: BrewDraft, text: str) -> list[dict[str, str]]:
    _enrich_brew_draft_from_text(draft, text)
    items: list[dict[str, str]] = []
    if draft.device:
        items.append({"category": "brewer", "name": draft.device})
    if draft.grinder:
        items.append({"category": "grinder", "name": draft.grinder})
    if draft.filter_media:
        items.append({"category": "filter_media", "name": draft.filter_media})
    if draft.water:
        items.append({"category": "water", "name": draft.water})

    # 用户单独说“我买了法压壶 / 我用 ZP6S”时，brew parse 可能没给草稿；再用关键词补一轮。
    fallback_pairs = [
        ("brewer", _first_pattern(text, _BREWER_PATTERNS)),
        ("grinder", _first_pattern(text, _GRINDER_PATTERNS)),
        ("filter_media", _first_pattern(text, _FILTER_PATTERNS)),
        ("water", _first_pattern(text, _WATER_PATTERNS)),
    ]
    existing = {(item["category"], item["name"].strip().lower()) for item in items}
    for category, name in fallback_pairs:
        if name and (category, name.strip().lower()) not in existing:
            items.append({"category": category, "name": name})
            existing.add((category, name.strip().lower()))
    return items


def _known_equipment_set(active_context: dict | None) -> set[tuple[str, str]]:
    known: set[tuple[str, str]] = set()
    for item in (active_context or {}).get("equipment_items") or []:
        if isinstance(item, dict) and item.get("category") and item.get("name"):
            known.add((str(item["category"]), str(item["name"]).strip().lower()))
    return known


def _contains_equipment_capture_hint(message: str) -> bool:
    return any(hint in (message or "") for hint in _EQUIPMENT_CAPTURE_HINTS)


async def _run_equipment_capture(
    message: str,
    *,
    model: str,
    gateway: ModelGateway | None,
    history: list[dict[str, str]] | None,
    active_context: dict | None,
) -> ActionResult:
    parse_text = _contextual_brew_text(message, history=history, active_recipe=(active_context or {}).get("recipe"))
    draft = await parse_brew_with_model(parse_text, model=model, gateway=gateway)
    source = "model"
    if draft is None:
        draft, _, _, _ = parse_brew_input(parse_text)
        source = "local"
    items = _equipment_items_from_draft(draft, parse_text)
    known = _known_equipment_set(active_context)
    new_items = [
        item for item in items
        if item.get("name") and (item["category"], item["name"].strip().lower()) not in known
    ]
    if not new_items:
        return ActionResult(
            type="equipment_capture",
            status="done",
            source=source,
            message="这件器具之前已经保存到「我的器具」了。若确实要再建一份，请明确说“仍然新建”。",
        )
    label_text = "、".join(f"{_EQUIPMENT_CATEGORY_LABELS.get(i['category'], i['category'])}：{i['name']}" for i in new_items)
    return ActionResult(
        type="equipment_capture",
        status="done",
        source=source,
        output={"items": new_items, "raw_input": message},
        message=f"我识别到新的器具：{label_text}。要存到「我的器具」吗？",
    )


def ensure_equipment_capture_for_brew(results: list[ActionResult], *, active_context: dict | None) -> None:
    if any(r.type == "equipment_capture" and isinstance(r.output, dict) and r.output.get("items") for r in results):
        return
    known = _known_equipment_set(active_context)
    for result in results:
        if result.type != "brew_record_parse" or not isinstance(result.output, dict):
            continue
        raw_draft = result.output.get("draft")
        if not isinstance(raw_draft, dict):
            continue
        try:
            draft = BrewDraft.model_validate(raw_draft)
        except Exception:
            continue
        text = str(result.output.get("raw_input") or "")
        items = _equipment_items_from_draft(draft, text)
        new_items = [
            item for item in items
            if item.get("name") and (item["category"], item["name"].strip().lower()) not in known
        ]
        if not new_items:
            continue
        label_text = "、".join(
            f"{_EQUIPMENT_CATEGORY_LABELS.get(i['category'], i['category'])}：{i['name']}" for i in new_items
        )
        results.append(
            ActionResult(
                type="equipment_capture",
                status="done",
                source=result.source,
                output={"items": new_items, "raw_input": text},
                message=f"这杯里有新的器具：{label_text}。要存到「我的器具」吗？",
            )
        )
        return


async def ensure_equipment_capture_result(
    results: list[ActionResult],
    *,
    message: str,
    model: str,
    gateway: ModelGateway | None = None,
    history: list[dict[str, str]] | None = None,
    active_context: dict | None = None,
) -> None:
    """端点级兜底：该存器具时，即使调度没派发，也补器具草稿卡。"""
    if any(r.type == "equipment_capture" and isinstance(r.output, dict) and r.output.get("items") for r in results):
        return

    ensure_equipment_capture_for_brew(results, active_context=active_context)
    if any(r.type == "equipment_capture" and isinstance(r.output, dict) and r.output.get("items") for r in results):
        return

    has_brew_draft = any(
        r.type == "brew_record_parse" and isinstance(r.output, dict) and r.output.get("draft")
        for r in results
    )
    if not (_contains_equipment_capture_hint(message) or has_brew_draft):
        return

    candidate = await _run_equipment_capture(
        message,
        model=model,
        gateway=gateway,
        history=history,
        active_context=active_context,
    )
    if isinstance(candidate.output, dict) and candidate.output.get("items"):
        results.append(candidate)
    elif _contains_equipment_capture_hint(message) and candidate.message:
        results.append(candidate)


async def _run_coach(
    action_type: str,
    *,
    message: str,
    active_context: dict | None,
    session_state: dict | None,
    image_urls: list[str] | None,
    settings: Settings,
    model: str,
    history: list[dict[str, str]] | None = None,
    gateway: ModelGateway | None,
) -> ActionResult:
    # active 实体（端点层按 active_*_id 从库里水合好）分别喂冲煮教练；不可用即本地保守兜底。
    ctx = active_context or {}
    text = await coach_with_model(
        message=message,
        active_bean=ctx.get("bean"),
        active_equipment=ctx.get("equipment"),
        active_recipe=ctx.get("recipe"),
        image_urls=image_urls,
        taste_feedback=(session_state or {}).get("taste_feedback"),
        history=history,
        model=model,
        vision_model=settings.vision_model,
        gateway=gateway,
    )
    if text:
        return ActionResult(type=action_type, status="done", source="model", message=text)
    return ActionResult(type=action_type, status="done", source="local", message=LOCAL_COACH_FALLBACK)


async def _run_web_verify(
    message: str,
    *,
    attachments: list[dict[str, Any]] | None,
    image_urls: list[str] | None,
    session_state: dict | None,
    knowledge_service: KnowledgeService,
    settings: Settings,
    model: str,
    history: list[dict[str, str]] | None = None,
    gateway: ModelGateway | None,
) -> ActionResult:
    """先试真联网检索（Brave Search）+ 模型综合；不可用 / 无结果 / 失败即降级回知识库（§9）。"""
    image_context: dict | None = None
    if image_urls and settings.vision_model:
        image_context = await understand_image(
            message=message,
            images=image_urls,
            session_state=session_state,
            vision_model=settings.vision_model,
            gateway=gateway,
        )

    if settings.web_search_enabled:
        try:
            search_text = message
            if image_context:
                search_text = f"{message}\n图片线索：{image_context}"
            sources = await web_search.search(
                web_search.build_search_query(search_text),
                api_key=settings.brave_api_key,
                count=settings.brave_search_count,
            )
            if sources:
                answer = await web_verify.verify_with_model(
                    message,
                    sources,
                    model=model,
                    image_context=image_context,
                    image_urls=image_urls,
                    history=history,
                    vision_model=settings.vision_model,
                    gateway=gateway,
                )
                if answer:
                    return ActionResult(
                        type="web_verify",
                        status="done",
                        source="model",
                        output={"answer": answer, "sources": [s.model_dump() for s in sources]},
                        message=answer,
                    )
        except Exception as exc:  # noqa: BLE001 — 联网链路任一步失败都降级，不打断对话
            logger.warning("web_verify online path failed, degrade to KB: %s", exc)

    # 降级：退回本地知识库回答，并明确标注非联网核实结果。
    kb = await _run_knowledge(
        message,
        image_urls=image_urls,
        history=history,
        knowledge_service=knowledge_service,
        settings=settings,
        model=model,
        gateway=gateway,
    )
    return ActionResult(
        type="web_verify",
        status="degraded",
        source=kb.source,
        output=kb.output,
        message=f"{_WEB_VERIFY_DISCLAIMER}\n{kb.message or ''}".strip(),
    )
