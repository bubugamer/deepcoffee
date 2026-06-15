"""Coffea 统一聊天入口：前端所有自然语言 / 图片消息先进入调度器。

POST /v1/coffea/messages —— 维护会话状态、跑 coffea_dispatch、记 usage + trace，
返回一个「路由计划」。专项能力的实际执行在后续 Phase 接入；本端点先把「会话状态 +
动作路由 + trace」跑通（见 docs/deepcoffee-ai-prompts.md §1，实现计划第 2 步）。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_ai_quota, require_member
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import AuthenticatedUser, get_current_user
from app.models.tables import UserEquipmentProfile
from app.repositories.beans import bean_repository
from app.repositories.brews import brew_record_repository
from app.repositories.coffea_sessions import coffea_session_repository
from app.repositories.equipment import equipment_repository
from app.repositories.profiles import profile_repository
from app.repositories.usage import ai_usage_repository
from app.repositories.user_memories import user_memory_repository
from app.schemas.bean import Bean, BeanDraft
from app.schemas.coffea import (
    ActionResult,
    CoffeaMessageRequest,
    CoffeaMessageResponse,
    CoffeaSessionHistory,
    CoffeaSessionState,
    CoffeaSessionTurn,
    UserMemoryItem,
    UserMemoryList,
    UserMemoryUpdate,
)
from app.services import coffea_dispatch
from app.services.bean_card_intake import summarize_draft
from app.services.brew_coach import coach_with_model
from app.services.candidate_service import candidate_service
from app.services.coffea_executor import assemble_reply, execute_plan
from app.services.memory_context import build_memory_context
from app.services.memory_maintenance import run_memory_maintenance
from app.services.image_storage import upload_chat_images
from app.services.knowledge_service import KnowledgeService, get_knowledge_service
from app.services.langfuse_client import langfuse_tracer

router = APIRouter(prefix="/coffea", tags=["coffea"], dependencies=[Depends(require_member)])

# 每多少轮对话后台抽取一次用户画像（控成本，不每轮都调模型）。
_EXTRACT_EVERY = 6

# 持久化到历史时，results 只保留展示安全字段；剥离草稿/原图/原始 OCR 等交互态与大字段。
_SAFE_OUTPUT_KEYS = frozenset({"sources", "bean_id", "auto_saved"})


# 识图建卡后判断用户这句话是否在要冲煮方案/建议。
_BREW_PLAN_HINTS = ("方案", "建议", "怎么冲", "冲煮", "热冲", "配方", "参数", "recipe", "冲一", "做一杯")


def _wants_brew_plan(message: str) -> bool:
    low = (message or "").lower()
    return any(k in low for k in _BREW_PLAN_HINTS)


async def _brew_advice_for_new_bean(
    session: AsyncSession,
    *,
    user_id: str,
    bean_id: str,
    message: str,
    equipment: list[UserEquipmentProfile],
    settings: Settings,
    trace_id: str,
) -> str | None:
    """识图建卡后给冲煮建议：有默认器具按它给方案；没有则引导用户去设默认器具。"""
    default_equip = next((e for e in equipment if e.is_default), None)
    if default_equip is None:
        return "想要冲煮方案的话，先到「我的器具」设一套默认器具，我就能按你的器具给你一版热冲方案。"
    bean = await bean_repository.get(session, user_id=user_id, bean_id=bean_id)
    if bean is None:
        return None
    advice = await coach_with_model(
        message=message,
        active_bean=bean.model_dump(mode="json"),
        active_equipment=_equipment_dict(default_equip),
        model=settings.model_default_model,
        vision_model=settings.vision_model,
    )
    if advice:
        await ai_usage_repository.record(session, user_id=user_id, action="coffea_brew_advice", trace_id=trace_id)
    return advice


def _display_safe_results(results: list[ActionResult]) -> list[dict]:
    safe: list[dict] = []
    for r in results:
        item: dict = {"type": r.type, "status": r.status, "message": r.message}
        output = r.output if isinstance(r.output, dict) else None
        if output:
            kept = {k: v for k, v in output.items() if k in _SAFE_OUTPUT_KEYS}
            if kept:
                item["output"] = kept
        safe.append(item)
    return safe


def _equipment_dict(e: UserEquipmentProfile) -> dict[str, str | bool | None]:
    """器具 ORM → 喂模型的紧凑 dict（Bean/BrewRecord 是 pydantic，直接 model_dump）。"""
    return {
        "id": e.id,
        "brew_method": e.brew_method,
        "grinder": e.grinder,
        "filter_media": e.filter_media,
        "water": e.water,
        "label": e.label,
        "is_default": e.is_default,
    }


async def _autosave_bean_card(
    session: AsyncSession,
    *,
    user_id: str,
    results: list[ActionResult],
    existing_beans: list[Bean],
    trace_id: str,
) -> str | None:
    """高识别度豆卡识图直接建档；同名豆已存在则降级为草稿确认，避免重复建档。

    成功落库时改写该 result 的 message/output（前端只见最终结果，不见草稿与原始判定）。
    """
    for result in results:
        if result.type != "read_bean_card_image" or result.status != "done":
            continue
        output = result.output or {}
        if not output.get("auto_save_eligible") or not isinstance(output.get("draft"), dict):
            continue
        draft = BeanDraft(**output["draft"])
        summary = summarize_draft(draft)
        name = (draft.name or "").strip()
        if any(b.name.strip() == name for b in existing_beans):
            output["auto_save_eligible"] = False
            result.message = (
                f"我从图片里识别到：{summary}。你的豆仓里已有同名豆子，"
                "为避免重复建档，请在下面的草稿卡里确认后再保存。"
            )
            continue
        bean_id = await bean_repository.create(
            session,
            user_id=user_id,
            draft=draft,
            source_type="image",
            raw_input=output.get("raw_input"),
            trace_id=trace_id,
        )
        # 与 /beans/confirm 同步：抽公共实体候选进管理员审核链路；失败不阻断建档。
        await candidate_service.extract_from_bean(session, user_id=user_id, bean_id=bean_id, trace_id=trace_id)
        confidence = output.get("confidence")
        pct = f"（识别度 {round(confidence * 100)}%）" if isinstance(confidence, (int, float)) else ""
        result.message = f"已识别并录入这支豆子：{summary}{pct}。已保存到你的豆仓，可随时打开豆卡修改。"
        result.output = {"bean_id": bean_id, "confidence": confidence, "auto_saved": True}
        return bean_id
    return None


@router.post("/messages", response_model=CoffeaMessageResponse, dependencies=[Depends(require_ai_quota)])
async def post_message(
    payload: CoffeaMessageRequest,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    knowledge_service: KnowledgeService = Depends(get_knowledge_service),
) -> CoffeaMessageResponse:
    # trace 耗时起点：覆盖整轮处理（水合上下文 + 调度 + 执行 + 落库），交给 Langfuse 算 duration。
    trace_started_at = datetime.now(timezone.utc)

    # 确保用户档案存在（会话表外键依赖 user_profiles）。
    await profile_repository.get_or_create(session, user.id, user.email)
    cs = await coffea_session_repository.get_or_create(
        session, user_id=user.id, session_id=payload.session_id
    )

    attachments = [a.model_dump(exclude_none=True) for a in payload.attachments]

    # 水合该用户自己的上下文：一次查询，既喂调度器（让路由更准）又选出 active 实体（喂冲煮教练）。
    # 隐私：只发该用户本人的消息 / 会话状态 / 豆·记录·器具，绝不带其他用户数据。
    state = cs.state or {}
    beans, _ = await bean_repository.list(session, user_id=user.id)
    brews, _ = await brew_record_repository.list(session, user_id=user.id, page=1, page_size=5)
    equipment = await equipment_repository.list_for_user(session, user.id)

    active_bean = next((b for b in beans if b.bean_id == state.get("active_bean_id")), None)
    active_recipe_id = state.get("active_recipe_id") or state.get("active_brew_id")
    active_recipe = (
        await brew_record_repository.get(session, user_id=user.id, record_id=active_recipe_id)
        if active_recipe_id
        else None
    )
    active_equipment = next((e for e in equipment if e.id == state.get("active_equipment_id")), None)
    active_context = {
        "bean": active_bean.model_dump(mode="json") if active_bean else None,
        "recipe": active_recipe.model_dump(mode="json") if active_recipe else None,
        "equipment": _equipment_dict(active_equipment) if active_equipment else None,
    }

    # 记忆注入层：把最近对话（L1）+ 用户画像（L3）汇总成可注入形态，一次构造、分发给调度器与各能力。
    user_memories = await user_memory_repository.list_active(session, user.id)
    mc = build_memory_context(cs, user_memories=user_memories)

    plan = await coffea_dispatch.dispatch(
        message=payload.message,
        attachments=attachments,
        session_state=cs.state,
        recent_beans=[b.model_dump(mode="json") for b in beans[:5]],
        recent_brews=[b.model_dump(mode="json") for b in brews],
        equipment_profiles=[_equipment_dict(e) for e in equipment],
        taste_preferences=mc.profile_text or state.get("taste_feedback"),
        recent_dialog=mc.history_text,
        model=settings.model_default_model,
    )

    # 按计划执行能现在执行的动作（knowledge / 图片 / 教练 / 联网核实）；其余标 pending。
    results = await execute_plan(
        plan,
        message=payload.message,
        attachments=attachments,
        session_state=cs.state,
        knowledge_service=knowledge_service,
        settings=settings,
        model=settings.model_default_model,
        active_context=active_context,
        history=mc.history_messages,
    )

    trace_id = f"coffea_dispatch_{uuid4().hex[:12]}"

    # 先把图片上传到 Supabase 图床，拿到公开 URL 用于跨设备展示，也用于 Langfuse trace metadata。
    image_urls = await upload_chat_images(attachments, user_id=user.id, settings=settings)

    # 高识别度豆卡自动录入（执行器只判定 auto_save_eligible，落库在端点层，保持执行器无副作用）。
    auto_saved_bean_id = await _autosave_bean_card(
        session, user_id=user.id, results=results, existing_beans=beans, trace_id=trace_id
    )

    # 落会话：合并状态更新 + 追加本轮用户消息（按预算裁剪）。
    coffea_session_repository.apply_state_updates(cs, plan.state_updates)
    if auto_saved_bean_id:
        coffea_session_repository.apply_state_updates(cs, {"active_bean_id": auto_saved_bean_id})
        await ai_usage_repository.record(
            session, user_id=user.id, action="coffea_bean_autosave", trace_id=trace_id
        )
    await session.flush()
    await ai_usage_repository.record(session, user_id=user.id, action="coffea_dispatch", trace_id=trace_id)
    # 真执行了知识/图片能力的，各记一条用量，便于分析。
    for result in results:
        if result.status == "done":
            await ai_usage_repository.record(
                session, user_id=user.id, action=f"coffea_{result.type}", trace_id=trace_id
            )
    # 前端只读 reply 作为主气泡正文；results 保留动作明细，不要求前端遍历 results 来找主回复。
    reply = assemble_reply(plan, results)

    # 服务端模型 key 配额/欠费导致的降级必须显式告知（否则 AI 只是静默变笨）；
    # 这是管理员要充值的事，不是用户额度问题，文案不引导用户充值。
    if plan.degrade_reason == "provider_quota":
        notice = "AI 服务暂时不可用，本次为基础回复。"
        reply = f"{reply}\n\n{notice}" if reply else notice

    # 识图建卡 + 用户这句话有"要冲煮方案"意图时，顺带给一段建议：
    # 有默认器具就按默认器具给方案；没有就引导去设默认器具。
    if auto_saved_bean_id and _wants_brew_plan(payload.message):
        advice = await _brew_advice_for_new_bean(
            session,
            user_id=user.id,
            bean_id=auto_saved_bean_id,
            message=payload.message,
            equipment=equipment,
            settings=settings,
            trace_id=trace_id,
        )
        if advice:
            reply = f"{reply}\n\n{advice}" if reply else advice

    # 落历史（跨设备同步）：用户一轮 + 助手一轮。图片传到 Supabase 图床存公开 URL（跨设备可看）。
    now_ms = int(time.time() * 1000)
    # image_urls 已在上面（trace 用）上传过，这里直接复用。
    dropped: list[dict] = []
    dropped += coffea_session_repository.append_turn(
        cs, "user", payload.message, at=now_ms, images=image_urls or None
    )
    if reply or results:
        dropped += coffea_session_repository.append_turn(
            cs, "assistant", reply or "", results=_display_safe_results(results), at=now_ms
        )
    # 轮次计数 → 决定本轮是否后台抽取用户画像（每 _EXTRACT_EVERY 轮一次，控成本）。
    turn_count = int((cs.state or {}).get("turn_count") or 0) + 1
    coffea_session_repository.apply_state_updates(cs, {"turn_count": turn_count})
    do_extract = turn_count % _EXTRACT_EVERY == 0
    await session.flush()

    # Langfuse trace 放在最后：output 取最终 reply（含降级提示/冲煮建议），
    # input/output 用自然语言，计划/结果/图片放 metadata；start/end 让 Langfuse 算 duration。
    langfuse_tracer.trace(
        "coffea_dispatch",
        trace_id=trace_id,
        user_id=user.id,
        input=payload.message,
        output=reply,
        metadata={
            "source": plan.source,
            "session_id": cs.session_id,
            "primary_intent": plan.primary_intent,
            "has_attachments": bool(attachments),
            "image_urls": image_urls or [],
            "plan": plan.model_dump(),
            "executed": [{"type": r.type, "status": r.status, "source": r.source} for r in results],
        },
        start_time=trace_started_at,
        end_time=datetime.now(timezone.utc),
    )

    # 记忆后台维护（L2 摘要 + L3 抽取）：响应返回后异步跑、独立 session，绝不阻塞或影响本轮对话。
    if dropped or do_extract:
        background_tasks.add_task(
            run_memory_maintenance,
            user_id=user.id,
            session_id=cs.session_id,
            dropped_turns=dropped,
            do_extract=do_extract,
            model=settings.model_default_model,
        )

    return CoffeaMessageResponse(
        session_id=cs.session_id,
        primary_intent=plan.primary_intent,
        secondary_intents=plan.secondary_intents,
        actions=plan.actions,
        results=results,
        state=CoffeaSessionState(**(cs.state or {})),
        reply=reply,
        should_answer_directly=plan.should_answer_directly,
        source=plan.source,
        trace_id=trace_id,
    )


@router.get("/session", response_model=CoffeaSessionHistory)
async def get_session_history(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CoffeaSessionHistory:
    """该用户那条永久对话的完整历史（跨设备同步:任意设备打开都看同一份）。"""
    await profile_repository.get_or_create(session, user.id, user.email)
    cs = await coffea_session_repository.get_or_create_user_session(session, user_id=user.id)
    turns: list[CoffeaSessionTurn] = []
    for m in cs.recent_messages or []:
        if not isinstance(m, dict):
            continue
        turns.append(
            CoffeaSessionTurn(
                role=m.get("role", "assistant"),
                text=m.get("content"),
                results=m.get("results") or [],
                at=m.get("at"),
                images=m.get("images") or [],
            )
        )
    return CoffeaSessionHistory(
        session_id=cs.session_id,
        state=CoffeaSessionState(**(cs.state or {})),
        turns=turns,
    )


def _memory_item(m) -> UserMemoryItem:
    return UserMemoryItem(
        id=m.id,
        kind=m.kind,
        content=m.content,
        confidence=m.confidence,
        source=m.source,
        status=m.status,
        created_at=m.created_at,
    )


@router.get("/memories", response_model=UserMemoryList)
async def list_memories(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserMemoryList:
    """该用户的长期记忆（L3 画像），供「我的口味档案」展示。"""
    await profile_repository.get_or_create(session, user.id, user.email)
    rows = await user_memory_repository.list_active(session, user.id)
    return UserMemoryList(memories=[_memory_item(m) for m in rows])


@router.patch("/memories/{memory_id}", response_model=UserMemoryItem)
async def update_memory(
    memory_id: str,
    payload: UserMemoryUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserMemoryItem:
    """用户修正一条记忆内容。"""
    m = await user_memory_repository.update_content(
        session, user_id=user.id, memory_id=memory_id, content=payload.content
    )
    if m is None:
        raise HTTPException(status_code=404, detail="memory_not_found")
    return _memory_item(m)


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """用户删除一条记忆（置 dismissed，不物理删）。"""
    ok = await user_memory_repository.dismiss(session, user_id=user.id, memory_id=memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="memory_not_found")
    return {"ok": True}
