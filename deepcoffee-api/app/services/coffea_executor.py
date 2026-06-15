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
_INTENT_ONLY = frozenset({"direct_answer", "ask_clarification", "out_of_scope"})
_DISPLAYABLE_RESULT_STATUSES = frozenset({"done", "degraded"})
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
    for action in plan.actions:
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
                results.append(await _run_brew_parse(message, model=model, gateway=gateway))
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
    """
    if plan.primary_intent in _INTENT_ONLY:
        return plan.direct_reply

    primary_result = next(
        (
            r.message
            for r in results
            if r.type == plan.primary_intent
            and r.status in _DISPLAYABLE_RESULT_STATUSES
            and r.message
        ),
        None,
    )
    if primary_result:
        return primary_result

    first_result = next(
        (
            r.message
            for r in results
            if r.status in _DISPLAYABLE_RESULT_STATUSES and r.message
        ),
        None,
    )
    return first_result or plan.direct_reply


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
    if kb.from_knowledge_base:
        grounding = knowledge_service.build_grounding([f.slug for f in kb.selected_files], settings)
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
    if not draft.name:
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
    if draft.device:
        parts.append(draft.device)
    grind = f"{draft.grinder or ''} {draft.grind_setting or ''}".strip()
    if grind:
        parts.append(grind)
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


async def _run_brew_parse(message: str, *, model: str, gateway: ModelGateway | None) -> ActionResult:
    """聊天里记录冲煮：消息带参数就真解析成草稿（缺什么明确说），落库由用户在草稿卡确认。

    完全没解析出参数（纯意图，如「我想记录冲煮」）才回通用引导语。
    """
    draft = await parse_brew_with_model(message, model=model, gateway=gateway)
    source = "model"
    if draft is None:
        draft, _, _, _ = parse_brew_input(message)
        source = "local"
    confidence, missing, _ = assess_brew_draft(draft)
    # 「实质参数」不含 bean_name：本地启发式几乎任何句子都能抽出个"豆名"，
    # 纯意图消息（"我想记录冲煮"）必须仍走通用引导，而不是抱着垃圾豆名出草稿。
    has_substance = any([
        draft.device, draft.grinder, draft.grind_setting, draft.dose_g, draft.water_ml,
        draft.water_temp_c, draft.ratio, draft.brew_time_seconds, draft.brew_steps,
    ])
    if not has_substance:
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
