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
from app.repositories.equipment import equipment_repository
from app.repositories.profiles import profile_repository
from app.repositories.usage import ai_usage_repository
from app.schemas.brew import (
    BrewComparisonItem,
    BrewConfirmRequest,
    BrewConfirmResponse,
    BrewDraft,
    BrewRecordCreateRequest,
    BrewDeleteResponse,
    BrewParseRequest,
    BrewParseResponse,
    BrewRecord,
    BrewRecordListResponse,
    BrewRecordUpdateRequest,
)
from app.schemas.bean import Bean, BeanUpdateRequest
from app.services.brew_parse_ai import parse_brew_with_model
from app.services.brew_recap_ai import recap_with_model
from app.services.brew_validation import complete_brew_parameters, validate_confirm_draft
from app.services.input_parser import assess_brew_draft, parse_brew_input
from app.services.langfuse_client import langfuse_tracer
from app.services.recap_service import build_local_recap

router = APIRouter(prefix="/brew", tags=["brew"], dependencies=[Depends(require_member)])


async def _upsert_record_equipment(session: AsyncSession, *, user_id: str, record: BrewRecordCreateRequest | BrewRecordUpdateRequest) -> None:
    mapping = [
        ("brewer", getattr(record, "device", None)),
        ("grinder", getattr(record, "grinder", None)),
        ("filter_media", getattr(record, "filter_media", None)),
        ("water", getattr(record, "water", None)),
    ]
    for category, name in mapping:
        if isinstance(name, str) and name.strip():
            await equipment_repository.upsert(session, user_id=user_id, category=category, name=name.strip())


def _draft_from_manual(bean: Bean, payload: BrewRecordCreateRequest) -> BrewDraft:
    draft = BrewDraft(
        bean_name=bean.name,
        origin=bean.origin,
        roaster=bean.roaster,
        process=bean.process,
        varietal="、".join(bean.varietal) or None,
        brew_method=payload.brew_method,
        device=payload.device,
        grinder=payload.grinder,
        grind_setting=payload.grind_setting,
        filter_media=payload.filter_media,
        water=payload.water,
        dose_g=payload.dose_g,
        water_ml=payload.water_ml,
        water_temp_c=payload.water_temp_c,
        brew_time=payload.brew_time,
        brew_time_seconds=payload.brew_time_seconds,
        brew_steps=payload.brew_steps,
        notes=payload.notes,
    )
    if draft.dose_g is not None and draft.water_ml is not None:
        return complete_brew_parameters(draft)
    return draft


@router.post("/parse", response_model=BrewParseResponse, dependencies=[Depends(require_ai_quota)])
async def parse_brew(
    payload: BrewParseRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BrewParseResponse:
    # 有模型用模型抽取，失败即回退本地正则；两条路径都用 assess_brew_draft 算 confidence。
    model_draft = await parse_brew_with_model(payload.input, model=settings.model_default_model)
    if model_draft is not None:
        draft = model_draft
        confidence, low_confidence_fields, clarification = assess_brew_draft(draft)
        source = "model"
    else:
        draft, confidence, low_confidence_fields, clarification = parse_brew_input(payload.input)
        source = "local"
    trace_id = f"brew_parse_{uuid4().hex[:12]}"
    await ai_usage_repository.record(session, user_id=user.id, action="brew_parse", trace_id=trace_id)
    langfuse_tracer.trace(
        "brew_parse",
        trace_id=trace_id,
        user_id=user.id,
        input=payload.input,
        output=draft.model_dump(exclude_none=True),
        metadata={"confidence": confidence, "low_confidence_fields": low_confidence_fields, "source": source},
    )
    return BrewParseResponse(
        draft=draft,
        confidence=confidence,
        low_confidence_fields=low_confidence_fields,
        clarification=clarification,
        source=source,
        trace_id=trace_id,
    )


@router.post("/confirm", response_model=BrewConfirmResponse, dependencies=[Depends(require_ai_quota)])
async def confirm_brew(
    payload: BrewConfirmRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BrewConfirmResponse:
    draft = validate_confirm_draft(payload.draft)
    trace_id = f"brew_confirm_{uuid4().hex[:12]}"
    # 有模型用模型复盘，失败即回退本地模板。
    model_recap = await recap_with_model(draft, model=settings.model_default_model)
    if model_recap is not None:
        recap, suggestions = model_recap
        source = "model"
    else:
        recap, suggestions = build_local_recap(draft)
        source = "local"
    await profile_repository.get_or_create(session, user.id, user.email)
    await ai_usage_repository.record(session, user_id=user.id, action="brew_confirm", trace_id=trace_id)
    record = await brew_record_repository.create(
        session,
        user_id=user.id,
        draft=draft,
        source_type=payload.source_type,
        raw_input=payload.raw_input,
        recap=recap,
        suggestions=suggestions,
        trace_id=trace_id,
        bean_card_id=payload.bean_card_id,
    )
    if payload.bean_card_id and draft.evaluation:
        await bean_repository.update(
            session,
            user_id=user.id,
            bean_id=payload.bean_card_id,
            payload=BeanUpdateRequest(rating=draft.evaluation),
        )
    langfuse_tracer.trace(
        "brew_recap",
        trace_id=trace_id,
        user_id=user.id,
        input=draft.model_dump(exclude_none=True),
        output={"recap": recap, "suggestions": suggestions},
        metadata={"brew_id": record.id, "source": source},
    )
    return BrewConfirmResponse(
        brew_id=record.id,
        recap=recap,
        suggestions=suggestions,
        source=source,
        trace_id=trace_id,
    )


@router.post("/records", response_model=BrewRecord)
async def create_brew_record(
    payload: BrewRecordCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrewRecord:
    bean = await bean_repository.get(session, user_id=user.id, bean_id=payload.bean_card_id)
    if bean is None:
        raise AppError(404, "bean_not_found", "Bean not found.")
    await profile_repository.get_or_create(session, user.id, user.email)
    await _upsert_record_equipment(session, user_id=user.id, record=payload)
    if payload.bean_rating is not None:
        await bean_repository.update(
            session,
            user_id=user.id,
            bean_id=payload.bean_card_id,
            payload=BeanUpdateRequest(rating=payload.bean_rating),
        )
    draft = _draft_from_manual(bean, payload)
    record = await brew_record_repository.create(
        session,
        user_id=user.id,
        draft=draft,
        source_type="manual",
        raw_input=None,
        recap=None,
        suggestions=[],
        trace_id=f"brew_manual_{uuid4().hex[:12]}",
        bean_card_id=payload.bean_card_id,
        brew_score=payload.brew_score,
    )
    return await brew_record_repository.get(session, user_id=user.id, record_id=record.id) or record


@router.get("/records", response_model=BrewRecordListResponse)
async def list_brew_records(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, description="全字段搜索：豆名/产地/烘焙商/品种/器具/磨豆机/备注/原始输入"),
    bean: str | None = Query(default=None),
    device: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrewRecordListResponse:
    items, total = await brew_record_repository.list(
        session,
        user_id=user.id,
        page=page,
        page_size=page_size,
        q=q,
        bean=bean,
        device=device,
        date_from=date_from,
        date_to=date_to,
    )
    return BrewRecordListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/compare", response_model=list[BrewComparisonItem])
async def compare_brew_records(
    ids: str | None = Query(default=None),
    bean_name: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[BrewComparisonItem]:
    record_ids = [item.strip() for item in ids.split(",") if item.strip()] if ids else None
    records = await brew_record_repository.compare(
        session, user_id=user.id, record_ids=record_ids, bean_name=bean_name
    )
    active_id = record_ids[0] if record_ids else (records[0].id if records else None)
    return [
        BrewComparisonItem(
            id=record.id,
            date=record.created_at.date().isoformat(),
            bean_name=record.bean_name,
            device=record.device,
            grinder=record.grinder,
            grind_setting=record.grind_setting,
            dose_g=record.dose_g,
            water_ml=record.water_ml,
            ratio=record.ratio,
            ratio_value=record.ratio_value,
            water_temp_c=record.water_temp_c,
            brew_time_seconds=record.brew_time_seconds,
            brew_score=record.brew_score,
            overall_score=record.brew_score,
            active=record.id == active_id,
        )
        for record in records
    ]


@router.get("/records/{record_id}", response_model=BrewRecord)
async def get_brew_record(
    record_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrewRecord:
    record = await brew_record_repository.get(session, user_id=user.id, record_id=record_id)
    if not record:
        raise AppError(404, "brew_record_not_found", "Brew record not found.")
    return record


@router.patch("/records/{record_id}", response_model=BrewRecord)
async def update_brew_record(
    record_id: str,
    payload: BrewRecordUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrewRecord:
    current = await brew_record_repository.get(session, user_id=user.id, record_id=record_id)
    if not current:
        raise AppError(404, "brew_record_not_found", "Brew record not found.")
    if payload.bean_card_id and current.bean_card_id and payload.bean_card_id != current.bean_card_id:
        raise AppError(422, "bean_card_locked", "Bean card cannot be changed after a brew record is linked.")
    if "bean_rating" in payload.model_fields_set and not (current.bean_card_id or payload.bean_card_id):
        raise AppError(422, "bean_card_required", "Link a bean card before editing bean rating.")
    if payload.bean_card_id:
        bean = await bean_repository.get(session, user_id=user.id, bean_id=payload.bean_card_id)
        if bean is None:
            raise AppError(404, "bean_not_found", "Bean not found.")
    await _upsert_record_equipment(session, user_id=user.id, record=payload)
    record = await brew_record_repository.update(session, user_id=user.id, record_id=record_id, payload=payload)
    if not record:
        raise AppError(404, "brew_record_not_found", "Brew record not found.")
    return record


@router.delete("/records/{record_id}", response_model=BrewDeleteResponse)
async def delete_brew_record(
    record_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrewDeleteResponse:
    deleted = await brew_record_repository.delete(session, user_id=user.id, record_id=record_id)
    if not deleted:
        raise AppError(404, "brew_record_not_found", "Brew record not found.")
    return BrewDeleteResponse(deleted=True)
