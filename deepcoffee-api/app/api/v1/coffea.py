"""Coffea 统一聊天入口：前端所有自然语言 / 图片消息先进入调度器。

POST /v1/coffea/messages —— 维护会话状态、跑 coffea_dispatch、记 usage + trace，
返回一个「路由计划」。专项能力的实际执行在后续 Phase 接入；本端点先把「会话状态 +
动作路由 + trace」跑通（见 docs/deepcoffee-ai-prompts.md §1，实现计划第 2 步）。
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends
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
from app.schemas.coffea import CoffeaMessageRequest, CoffeaMessageResponse, CoffeaSessionState
from app.services import coffea_dispatch
from app.services.billing_service import billing_service
from app.services.coffea_executor import assemble_reply, execute_plan
from app.services.knowledge_service import KnowledgeService, get_knowledge_service
from app.services.langfuse_client import langfuse_tracer

router = APIRouter(prefix="/coffea", tags=["coffea"], dependencies=[Depends(require_member)])


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


@router.post("/messages", response_model=CoffeaMessageResponse, dependencies=[Depends(require_ai_quota)])
async def post_message(
    payload: CoffeaMessageRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    knowledge_service: KnowledgeService = Depends(get_knowledge_service),
) -> CoffeaMessageResponse:
    # 确保用户档案存在（会话表外键依赖 user_profiles）。
    await profile_repository.get_or_create(session, user.id, user.email)
    cs = await coffea_session_repository.get_or_create(
        session, user_id=user.id, session_id=payload.session_id
    )

    token = await billing_service.get_model_token(session, user.id)
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

    plan = await coffea_dispatch.dispatch(
        message=payload.message,
        attachments=attachments,
        session_state=cs.state,
        recent_beans=[b.model_dump(mode="json") for b in beans[:5]],
        recent_brews=[b.model_dump(mode="json") for b in brews],
        equipment_profiles=[_equipment_dict(e) for e in equipment],
        token=token,
        model=settings.new_api_default_model,
    )

    # 按计划执行能现在执行的动作（knowledge / 图片 / 教练 / 联网核实）；其余标 pending。
    results = await execute_plan(
        plan,
        message=payload.message,
        attachments=attachments,
        session_state=cs.state,
        knowledge_service=knowledge_service,
        settings=settings,
        token=token,
        model=settings.new_api_default_model,
        active_context=active_context,
    )

    # 落会话：合并状态更新 + 追加本轮用户消息（按预算裁剪）。
    coffea_session_repository.apply_state_updates(cs, plan.state_updates)
    coffea_session_repository.append_message(cs, "user", payload.message)
    await session.flush()

    trace_id = f"coffea_dispatch_{uuid4().hex[:12]}"
    await ai_usage_repository.record(session, user_id=user.id, action="coffea_dispatch", trace_id=trace_id)
    # 真执行了知识/图片能力的，各记一条用量，便于分析。
    for result in results:
        if result.status == "done":
            await ai_usage_repository.record(
                session, user_id=user.id, action=f"coffea_{result.type}", trace_id=trace_id
            )
    langfuse_tracer.trace(
        "coffea_dispatch",
        trace_id=trace_id,
        user_id=user.id,
        input=payload.message,
        output=plan.model_dump(),
        metadata={
            "source": plan.source,
            "session_id": cs.session_id,
            "primary_intent": plan.primary_intent,
            "has_attachments": bool(attachments),
            "executed": [{"type": r.type, "status": r.status, "source": r.source} for r in results],
        },
    )

    # 前端只读 reply 作为主气泡正文；results 保留动作明细，不要求前端遍历 results 来找主回复。
    reply = assemble_reply(plan, results)
    # 余额耗尽导致的降级必须显式告知（否则 AI 只是静默变笨，用户不知道找管理员充值）。
    if plan.degrade_reason == "balance_exhausted":
        reply = f"{reply}\n\nAI 余额不足，本次为基础回复。请联系管理员充值。" if reply else "AI 余额不足，本次为基础回复。请联系管理员充值。"

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
