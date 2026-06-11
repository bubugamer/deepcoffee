from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_ai_quota, require_member
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import AuthenticatedUser, get_current_user
from app.repositories.brews import brew_record_repository
from app.repositories.profiles import profile_repository
from app.repositories.usage import ai_usage_repository
from app.schemas.brew import (
    BrewComparisonItem,
    BrewConfirmRequest,
    BrewConfirmResponse,
    BrewDeleteResponse,
    BrewParseRequest,
    BrewParseResponse,
    BrewRecord,
    BrewRecordListResponse,
    BrewRecordUpdateRequest,
)
from app.services.brew_parse_ai import parse_brew_with_model
from app.services.brew_recap_ai import recap_with_model
from app.services.brew_validation import validate_confirm_draft
from app.services.input_parser import assess_brew_draft, parse_brew_input
from app.services.langfuse_client import langfuse_tracer
from app.services.recap_service import build_local_recap

router = APIRouter(prefix="/brew", tags=["brew"], dependencies=[Depends(require_member)])


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
            overall_score=record.evaluation.overall.score
            if record.evaluation and record.evaluation.overall
            else None,
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
