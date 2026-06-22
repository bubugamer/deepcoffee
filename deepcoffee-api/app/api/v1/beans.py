from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_ai_quota, require_member
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import AuthenticatedUser, get_current_user
from app.repositories.beans import bean_repository
from app.repositories.brews import brew_record_repository
from app.repositories.coffea_sessions import coffea_session_repository
from app.repositories.equipment import equipment_repository
from app.repositories.profiles import profile_repository
from app.repositories.usage import ai_usage_repository
from app.schemas.bean import (
    Bean,
    BeanConfirmRequest,
    BeanConfirmResponse,
    BeanListResponse,
    BeanParseRequest,
    BeanParseResponse,
    BeanUpdateRequest,
    RecommendationParams,
    RecommendEquipment,
    RecommendParamsRequest,
    RecommendParamsResponse,
    RecommendParamsTurnResponse,
    SetRecommendParamsRequest,
)
from app.schemas.brew import BrewDraft
from app.services.bean_parse_ai import parse_bean_with_model
from app.services.bean_parser import assess_bean_draft, parse_bean_input
from app.services.bean_recommend_service import evaluate_turn
from app.services.brew_validation import complete_brew_parameters
from app.services.candidate_service import candidate_service
from app.services.langfuse_client import langfuse_tracer

router = APIRouter(prefix="/beans", tags=["beans"], dependencies=[Depends(require_member)])


def _validate_required_bean_fields(draft: BeanConfirmRequest | BeanUpdateRequest) -> None:
    data = draft.draft if isinstance(draft, BeanConfirmRequest) else draft
    missing: list[str] = []
    if isinstance(draft, BeanConfirmRequest) and not (
        (data.name and data.name.strip())
        or (data.roaster_product_name and data.roaster_product_name.strip())
    ):
        missing.append("draft.name")
    for field in ("roaster_name", "origin_name", "process_name"):
        value = getattr(data, field, None)
        if not (isinstance(value, str) and value.strip()):
            missing.append(f"draft.{field}" if isinstance(draft, BeanConfirmRequest) else field)
    if missing:
        raise AppError(
            422,
            "bean_required_fields_missing",
            "确认建档前请填写烘焙商、产地和处理法。",
            details={"fields": missing},
        )


def _validate_update_required_fields(payload: BeanUpdateRequest, current: Bean) -> None:
    updates = payload.model_dump(exclude_unset=True)
    values = {
        "roaster_name": updates.get("roaster_name", current.roaster),
        "origin_name": updates.get("origin_name", current.origin),
        "process_name": updates.get("process_name", current.process),
    }
    missing = [field for field, value in values.items() if not (isinstance(value, str) and value.strip())]
    if missing:
        raise AppError(
            422,
            "bean_required_fields_missing",
            "请填写烘焙商、产地和处理法后再保存豆卡。",
            details={"fields": missing},
        )


@router.get("", response_model=BeanListResponse)
async def list_beans(
    q: str | None = Query(default=None, description="搜索豆名/烘焙商/产地/处理法"),
    process: str | None = Query(default=None),
    min_score: float | None = Query(default=None, ge=1, le=5),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BeanListResponse:
    items, total = await bean_repository.list(
        session, user_id=user.id, q=q, process=process, min_score=min_score
    )
    return BeanListResponse(items=items, total=total)


@router.post("/parse", response_model=BeanParseResponse, dependencies=[Depends(require_ai_quota)])
async def parse_bean(
    payload: BeanParseRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BeanParseResponse:
    # 有模型用模型抽取，失败即回退本地启发式；两条路径都用 assess_bean_draft 算 confidence。
    model_draft = await parse_bean_with_model(payload.input, model=settings.model_default_model)
    if model_draft is not None:
        draft = model_draft
        confidence, low_confidence_fields, clarification = assess_bean_draft(draft)
        source = "model"
    else:
        draft, confidence, low_confidence_fields, clarification = parse_bean_input(payload.input)
        source = "local"
    trace_id = f"bean_parse_{uuid4().hex[:12]}"
    await ai_usage_repository.record(session, user_id=user.id, action="bean_parse", trace_id=trace_id)
    langfuse_tracer.trace(
        "bean_parse",
        trace_id=trace_id,
        user_id=user.id,
        input=payload.input,
        output=draft.model_dump(exclude_none=True),
        metadata={"confidence": confidence, "low_confidence_fields": low_confidence_fields, "source": source},
    )
    return BeanParseResponse(
        draft=draft,
        confidence=confidence,
        low_confidence_fields=low_confidence_fields,
        clarification=clarification,
        source=source,
        trace_id=trace_id,
    )


@router.post("/confirm", response_model=BeanConfirmResponse)
async def confirm_bean(
    payload: BeanConfirmRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BeanConfirmResponse:
    _validate_required_bean_fields(payload)
    trace_id = f"bean_confirm_{uuid4().hex[:12]}"
    await profile_repository.get_or_create(session, user.id, user.email)
    bean_id = await bean_repository.create(
        session,
        user_id=user.id,
        draft=payload.draft,
        source_type=payload.source_type,
        raw_input=payload.raw_input,
        trace_id=trace_id,
    )
    # 自下而上：从确认后的豆卡里抽取可复用的公共实体事实，生成候选（走管理员审核链路）。
    # 主观风味/口味判断不在此列。候选生成失败不阻断建档。
    await candidate_service.extract_from_bean(session, user_id=user.id, bean_id=bean_id, trace_id=trace_id)
    langfuse_tracer.trace(
        "bean_confirm",
        trace_id=trace_id,
        user_id=user.id,
        input=payload.draft.model_dump(exclude_none=True),
        output={"bean_id": bean_id},
    )
    return BeanConfirmResponse(bean_id=bean_id, trace_id=trace_id)


@router.get("/{bean_id}", response_model=Bean)
async def get_bean(
    bean_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Bean:
    bean = await bean_repository.get(session, user_id=user.id, bean_id=bean_id)
    if bean is None:
        raise AppError(404, "bean_not_found", "Bean not found.")
    return bean


@router.patch("/{bean_id}", response_model=Bean)
async def update_bean(
    bean_id: str,
    payload: BeanUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Bean:
    current = await bean_repository.get(session, user_id=user.id, bean_id=bean_id)
    if current is None:
        raise AppError(404, "bean_not_found", "Bean not found.")
    _validate_update_required_fields(payload, current)
    bean = await bean_repository.update(session, user_id=user.id, bean_id=bean_id, payload=payload)
    await candidate_service.extract_from_bean(session, user_id=user.id, bean_id=bean_id, trace_id=f"bean_update_{uuid4().hex[:12]}")
    if bean is None:
        raise AppError(404, "bean_not_found", "Bean not found.")
    return bean


@router.delete("/{bean_id}")
async def delete_bean(
    bean_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    deleted = await bean_repository.delete(session, user_id=user.id, bean_id=bean_id)
    if not deleted:
        raise AppError(404, "bean_not_found", "Bean not found.")
    return {"deleted": True}


@router.post(
    "/{bean_id}/recommend-params",
    response_model=RecommendParamsTurnResponse,
    dependencies=[Depends(require_ai_quota)],
)
async def recommend_params(
    bean_id: str,
    payload: RecommendParamsRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RecommendParamsTurnResponse:
    """Coffea 多轮闭环：询问器具 → 信息够了生成建议（见 docs/deepcoffee-ai-prompts.md §5）。

    - needs_input：还缺器具，只保存会话状态，不落库。
    - completed：保存用户器具资料 + 建一条隐藏 ai_suggestion 冲煮记录，豆子指针指向它。
    - fallback：模型不可用且无可用器具上下文，只回提示、不落库。
    消耗 AI 额度。
    """
    bean = await bean_repository.get(session, user_id=user.id, bean_id=bean_id)
    if bean is None:
        raise AppError(404, "bean_not_found", "Bean not found.")
    await profile_repository.get_or_create(session, user.id, user.email)
    cs = await coffea_session_repository.get_or_create(session, user_id=user.id, session_id=payload.session_id)

    sub_key = f"recommend:{bean_id}"
    sub_state = (cs.state or {}).get(sub_key) or {}
    equipment_draft = sub_state.get("equipment_draft")
    prev_status = sub_state.get("status") or "needs_input"

    equipment_items = await equipment_repository.list_for_user(session, user.id)
    profile_dicts = [
        {
            "category": item.category,
            "name": item.name,
            "notes": item.notes,
            "is_default": item.is_default,
        }
        for item in equipment_items
    ]
    turn = await evaluate_turn(
        bean=bean,
        equipment_profiles=profile_dicts,
        equipment_draft=equipment_draft,
        message=payload.message,
        session_id=cs.session_id,
        status=prev_status,
        model=settings.model_default_model,
    )

    trace_id = f"bean_reco_{uuid4().hex[:12]}"
    recommended_record_id: str | None = None
    if turn.status == "completed" and turn.recommendation:
        rec = turn.recommendation
        draft = complete_brew_parameters(
            BrewDraft(
                bean_name=bean.name,
                origin=bean.origin,
                roaster=bean.roaster,
                process=bean.process,
                varietal="、".join(bean.varietal) or None,
                brew_method=turn.equipment.get("brew_method"),
                device=rec.get("device"),
                grinder=rec.get("grinder"),
                grind_setting=rec.get("grind_setting"),
                filter_media=rec.get("filter"),
                water=turn.equipment.get("water"),
                dose_g=rec.get("dose_g"),
                water_ml=rec.get("water_ml"),
                water_temp_c=rec.get("water_temp_c"),
                ratio=rec.get("ratio"),
                brew_time_seconds=rec.get("brew_time_seconds"),
                notes=rec.get("notes"),
            )
        )
        record = await brew_record_repository.create(
            session,
            user_id=user.id,
            draft=draft,
            source_type="ai_suggestion",
            raw_input=None,
            recap=f"Coffea 建议参数：{rec.get('notes') or ''}",
            suggestions=[],
            trace_id=trace_id,
            bean_card_id=bean_id,
            record_type="ai_suggestion",
            is_user_visible=False,
        )
        await bean_repository.set_recommended_record(
            session, user_id=user.id, bean_id=bean_id, record_id=record.id
        )
        recommended_record_id = record.id

    # 保存多轮子流程状态（统一在 coffea_sessions 一套 session_id 下）。
    new_state = dict(cs.state or {})
    new_state[sub_key] = {
        "equipment_draft": turn.equipment,
        "missing_fields": turn.missing_fields,
        "status": turn.status,
    }
    cs.state = new_state
    await session.flush()

    await ai_usage_repository.record(session, user_id=user.id, action="bean_recommend_params", trace_id=trace_id)
    langfuse_tracer.trace(
        "bean_recommend_params",
        trace_id=trace_id,
        user_id=user.id,
        input={"bean_id": bean_id, "message": payload.message},
        output={"status": turn.status, "source": turn.source, "recommendation": turn.recommendation},
        metadata={"missing_fields": turn.missing_fields, "intent": turn.intent},
    )

    return RecommendParamsTurnResponse(
        status=turn.status,
        intent=turn.intent,
        assistant_message=turn.assistant_message,
        session_id=cs.session_id,
        equipment=RecommendEquipment(**turn.equipment),
        missing_fields=turn.missing_fields,
        recommendation=RecommendationParams(**turn.recommendation) if turn.recommendation else None,
        recommended_record_id=recommended_record_id,
        source=turn.source,
        trace_id=trace_id,
    )


@router.put("/{bean_id}/recommend-params", response_model=RecommendParamsResponse)
async def set_recommend_params(
    bean_id: str,
    payload: SetRecommendParamsRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RecommendParamsResponse:
    """设置建议参数：指向用户某条冲煮记录（record_id），或手动给一组参数（params，
    落成隐藏 user_suggestion 记录）。二选一；都不消耗 AI 额度。"""
    if (payload.record_id is None) == (payload.params is None):
        raise AppError(422, "invalid_recommend_params", "Provide exactly one of record_id / params.")

    if payload.params is not None:
        # 手动路径：创建隐藏建议记录并把豆卡指过去（与 AI 生成共用同一指针机制）。
        trace_id = f"bean_manual_params_{uuid4().hex[:12]}"
        p = payload.params
        draft = BrewDraft(
            device=p.device,
            grinder=p.grinder,
            grind_setting=p.grind_setting,
            dose_g=p.dose_g,
            water_ml=p.water_ml,
            water_temp_c=p.water_temp_c,
            ratio=p.ratio,
            brew_time_seconds=p.brew_time_seconds,
            notes=p.notes,
        )
        record = await brew_record_repository.create(
            session,
            user_id=user.id,
            draft=draft,
            source_type="manual",
            raw_input=None,
            recap="手动设置的建议参数",
            suggestions=[],
            trace_id=trace_id,
            bean_card_id=bean_id,
            record_type="user_suggestion",
            is_user_visible=False,
        )
        record_id = record.id
    else:
        record = await brew_record_repository.get(session, user_id=user.id, record_id=payload.record_id)
        if record is None:
            raise AppError(404, "brew_record_not_found", "Brew record not found.")
        record_id = payload.record_id

    updated = await bean_repository.set_recommended_record(
        session, user_id=user.id, bean_id=bean_id, record_id=record_id
    )
    if updated is None:
        raise AppError(404, "bean_not_found", "Bean not found.")
    return RecommendParamsResponse(
        recommended_params=updated.recommended_params,
        recommended_record_id=record_id,
        trace_id=record.trace_id or "",
    )
