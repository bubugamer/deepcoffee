from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import AuthenticatedUser, require_admin
from app.models.tables import CandidateFact as CandidateFactORM
from app.models.tables import InviteCode, Proposal as ProposalORM, UserAiQuotaSetting, UserProfile
from app.repositories.admin_audit import admin_audit_repository
from app.repositories.candidates import candidate_repository
from app.repositories.entities import entity_repository
from sqlalchemy import func, select

from app.repositories.invites import InviteAlreadyUsedError, InviteRepository
from app.repositories.profiles import profile_repository
from app.repositories.usage import ai_usage_repository
from app.schemas.auth import (
    AdminAuditEventInfo,
    AdminStats,
    AdminUserInfo,
    AdminUserQuotaUpdateRequest,
    AdminUserUpdateRequest,
    InviteCodeInfo,
    InviteCreateRequest,
)
from app.schemas.candidate import (
    CandidateFact,
    CandidateMergeRequest,
    CandidatePromoteResponse,
    CandidateReviewRequest,
    SimilarEntity,
)
from app.schemas.entity import (
    DuplicateGroup,
    EntityDuplicatesResponse,
    EntityMergeRequest,
    EntityRenameRequest,
    PublicEntity,
)
from app.schemas.proposal import Proposal, ProposalMarkAppliedRequest, ProposalReviewRequest
from app.services.candidate_service import candidate_service
from app.services.knowledge_service import KnowledgeService, get_knowledge_service
from app.services.proposal_service import proposal_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/knowledge/reload")
async def reload_knowledge(
    service: KnowledgeService = Depends(get_knowledge_service),
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int | str]:
    service.reload()
    categories = service.list_categories()
    public_count = len(service.list_articles())
    indexable_count = len([document for document in service.articles.values() if document.indexable])
    return {
        "article_count": public_count,
        "public_article_count": public_count,
        "indexable_article_count": indexable_count,
        "scanned_markdown_count": len(service.articles),
        "category_count": len(categories),
        # reload 是 Markdown→DB；这里附带报告公共实体库当前 active 实体数，便于观察自下而上链路。
        "entity_count": await entity_repository.count(session, status="active"),
        "reloaded_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/invites", response_model=list[InviteCodeInfo])
async def create_invites(
    payload: InviteCreateRequest,
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[InviteCodeInfo]:
    repository = InviteRepository(default_codes=set())
    return await repository.create_codes(
        session, count=payload.count, expires_at=payload.expires_at, note=payload.note
    )


@router.get("/invites", response_model=list[InviteCodeInfo])
async def list_invites(
    status: str | None = Query(default=None),
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[InviteCodeInfo]:
    repository = InviteRepository(default_codes=set())
    return await repository.list(session, status=status)


@router.post("/invites/{code}/revoke", response_model=InviteCodeInfo)
async def revoke_invite(
    code: str,
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> InviteCodeInfo:
    repository = InviteRepository(default_codes=set())
    try:
        info = await repository.revoke(session, code)
    except InviteAlreadyUsedError:
        raise AppError(409, "invite_already_used", "邀请码已被使用，无法作废。")
    if info is None:
        raise AppError(404, "invite_not_found", "Invite code not found.")
    return info


@router.get("/stats", response_model=AdminStats)
async def admin_stats(
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminStats:
    async def _count(stmt) -> int:
        return int(await session.scalar(stmt) or 0)

    return AdminStats(
        user_count=await _count(select(func.count()).select_from(UserProfile)),
        active_invite_count=await _count(
            select(func.count()).select_from(InviteCode).where(InviteCode.status == "active")
        ),
        pending_proposal_count=await _count(
            select(func.count()).select_from(ProposalORM).where(ProposalORM.status == "pending")
        ),
        pending_candidate_count=await _count(
            select(func.count()).select_from(CandidateFactORM).where(CandidateFactORM.status == "pending_review")
        ),
        active_entity_count=await entity_repository.count(session, status="active"),
    )


@router.patch("/users/{user_id}", response_model=AdminUserInfo)
async def update_user(
    user_id: str,
    payload: AdminUserUpdateRequest,
    admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AdminUserInfo:
    if payload.plan is None and payload.role is None and payload.status is None:
        raise AppError(400, "empty_update", "Provide at least one of plan / role / status.")
    profile = await session.get(UserProfile, user_id)
    if profile is None:
        raise AppError(404, "user_not_found", "User profile not found.")
    # 防自锁：管理员不能撤掉自己的 admin、也不能禁用自己（避免唯一管理员把自己关在门外）。
    if user_id == admin.id and (payload.role == "user" or payload.status == "disabled"):
        raise AppError(400, "cannot_modify_self", "不能对自己执行降级或禁用操作。")
    # 审计：每个真实变化的字段各落一条（传相同值不记）。
    changes: list[tuple[str, str, str]] = []
    if payload.plan is not None and payload.plan != profile.plan:
        changes.append(("plan_change", profile.plan, payload.plan))
        profile.plan = payload.plan
    if payload.role is not None and payload.role != profile.role:
        changes.append(("role_change", profile.role, payload.role))
        profile.role = payload.role
    if payload.status is not None and payload.status != profile.status:
        changes.append(("status_change", profile.status, payload.status))
        profile.status = payload.status
    await session.flush()
    if changes:
        # 审计 actor 外键依赖操作者自己的档案存在（首次操作的环境名单管理员可能还没建档）。
        await profile_repository.get_or_create(session, admin.id, admin.email)
    for action, before, after in changes:
        await admin_audit_repository.record(
            session, user_id=user_id, actor_id=admin.id, action=action, before=before, after=after
        )
    await session.refresh(profile)
    return await profile_repository.admin_user_info(session, profile, settings=settings)


@router.get("/users", response_model=list[AdminUserInfo])
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[AdminUserInfo]:
    return await profile_repository.list_users_with_invites(session, settings=settings, page=page, page_size=page_size)


@router.patch("/users/{user_id}/quota", response_model=AdminUserInfo)
async def update_user_quota(
    user_id: str,
    payload: AdminUserQuotaUpdateRequest,
    admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AdminUserInfo:
    fields = payload.model_fields_set
    if "monthly_limit" not in fields and "used_this_month" not in fields:
        raise AppError(400, "empty_quota_update", "Provide monthly_limit or used_this_month.")
    profile = await session.get(UserProfile, user_id)
    if profile is None:
        raise AppError(404, "user_not_found", "User profile not found.")
    await profile_repository.get_or_create(session, admin.id, admin.email)
    if "monthly_limit" in fields:
        old_setting = await session.get(UserAiQuotaSetting, user_id)
        old_limit = old_setting.monthly_limit if old_setting is not None else None
        if old_limit != payload.monthly_limit:
            await admin_audit_repository.record(
                session,
                user_id=user_id,
                actor_id=admin.id,
                action="quota_limit_change",
                before="套餐默认" if old_limit is None else str(old_limit),
                after="套餐默认" if payload.monthly_limit is None else str(payload.monthly_limit),
                reason=payload.reason,
            )
        await profile_repository.set_quota(
            session,
            user_id=user_id,
            monthly_limit=payload.monthly_limit,
            actor_id=admin.id,
            reason=payload.reason,
        )
    if "used_this_month" in fields and payload.used_this_month is not None:
        old_used = await ai_usage_repository.effective_count_for(session, user_id)
        if old_used != payload.used_this_month:
            await admin_audit_repository.record(
                session,
                user_id=user_id,
                actor_id=admin.id,
                action="usage_adjust",
                before=str(old_used),
                after=str(payload.used_this_month),
                reason=payload.reason,
            )
        await ai_usage_repository.set_effective_count(
            session,
            user_id=user_id,
            used_this_month=payload.used_this_month,
            actor_id=admin.id,
            reason=payload.reason,
        )
    await session.refresh(profile)
    return await profile_repository.admin_user_info(session, profile, settings=settings)


@router.get("/users/{user_id}/audit", response_model=list[AdminAuditEventInfo])
async def list_user_audit(
    user_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AdminAuditEventInfo]:
    """「修改历史」：该用户被管理员修改的全部记录，按时间倒序。"""
    profile = await session.get(UserProfile, user_id)
    if profile is None:
        raise AppError(404, "user_not_found", "User profile not found.")
    rows = await admin_audit_repository.list_for_user(session, user_id, page=page, page_size=page_size)
    return [
        AdminAuditEventInfo(
            created_at=event.created_at,
            actor_email=actor_email,
            action=event.action,
            before_value=event.before_value,
            after_value=event.after_value,
            reason=event.reason,
        )
        for event, actor_email in rows
    ]


@router.get("/proposals", response_model=list[Proposal])
async def list_proposals(
    status: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[Proposal]:
    items = await proposal_service.list(session, status=status, entity_type=entity_type)
    start = (page - 1) * page_size
    return items[start : start + page_size]


@router.get("/proposals/{proposal_id}", response_model=Proposal)
async def get_proposal(
    proposal_id: str,
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Proposal:
    return await proposal_service.get(session, proposal_id)


@router.post("/proposals/{proposal_id}/approve", response_model=Proposal)
async def approve_proposal(
    proposal_id: str,
    payload: ProposalReviewRequest,
    admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Proposal:
    return await proposal_service.transition(
        session, proposal_id, status="approved", actor_id=admin.id, note=payload.reviewer_note
    )


@router.post("/proposals/{proposal_id}/reject", response_model=Proposal)
async def reject_proposal(
    proposal_id: str,
    payload: ProposalReviewRequest,
    admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Proposal:
    return await proposal_service.transition(
        session, proposal_id, status="rejected", actor_id=admin.id, note=payload.reviewer_note
    )


@router.post("/proposals/{proposal_id}/mark-applied", response_model=Proposal)
async def mark_proposal_applied(
    proposal_id: str,
    payload: ProposalMarkAppliedRequest,
    admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Proposal:
    return await proposal_service.transition(
        session,
        proposal_id,
        status="applied",
        actor_id=admin.id,
        note=payload.reviewer_note,
        applied_markdown_path=payload.applied_markdown_path,
    )


# ---- 候选事实审核（自下而上链路）----


async def _attach_similar(session: AsyncSession, facts: list[CandidateFact]) -> None:
    """给待审候选填充「疑似已有实体」（仅 pending_review，供管理员「并入」决策；不自动合）。"""
    for fact in facts:
        if fact.status != "pending_review":
            continue
        sims = await entity_repository.find_similar(session, fact.entity_type, fact.title)
        fact.similar_entities = [
            SimilarEntity(
                id=e.id, entity_type=e.entity_type, canonical_name=e.canonical_name, status=e.status
            )
            for e in sims
        ]


@router.get("/candidates", response_model=list[CandidateFact])
async def list_candidates(
    status: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[CandidateFact]:
    items = await candidate_repository.list(session, status=status, entity_type=entity_type)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]
    await _attach_similar(session, page_items)
    return page_items


@router.get("/candidates/{candidate_id}", response_model=CandidateFact)
async def get_candidate(
    candidate_id: str,
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CandidateFact:
    row = await candidate_repository.get_orm(session, candidate_id)
    if row is None:
        raise AppError(404, "candidate_not_found", "Candidate fact not found.")
    fact = CandidateFact.model_validate(row)
    await _attach_similar(session, [fact])
    return fact


@router.post("/candidates/{candidate_id}/promote", response_model=CandidatePromoteResponse)
async def promote_candidate(
    candidate_id: str,
    payload: CandidateReviewRequest,
    admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CandidatePromoteResponse:
    result = await candidate_service.promote_to_proposal(
        session, candidate_id, reviewer_id=admin.id, note=payload.reviewer_note
    )
    if result is None:
        raise AppError(404, "candidate_not_found", "Candidate fact not found.")
    candidate_id, proposal_id = result
    return CandidatePromoteResponse(candidate_id=candidate_id, proposal_id=proposal_id, status="promoted")


@router.post("/candidates/{candidate_id}/merge", response_model=CandidateFact)
async def merge_candidate(
    candidate_id: str,
    payload: CandidateMergeRequest,
    admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CandidateFact:
    """把候选「并入」已有实体：候选名登记为该实体别名、候选标记 merged，不建新实体。"""
    result = await candidate_service.merge_candidate_into_entity(
        session, candidate_id, entity_id=payload.entity_id, reviewer_id=admin.id, note=payload.reviewer_note
    )
    if result is None:
        raise AppError(404, "candidate_or_entity_not_found", "候选或目标实体不存在。")
    return result


@router.post("/candidates/{candidate_id}/reject", response_model=CandidateFact)
async def reject_candidate(
    candidate_id: str,
    payload: CandidateReviewRequest,
    admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CandidateFact:
    candidate = await candidate_repository.reject(
        session, candidate_id, reviewer_id=admin.id, note=payload.reviewer_note
    )
    if candidate is None:
        raise AppError(404, "candidate_not_found", "Candidate fact not found.")
    return candidate


# ---- 公共实体库（只读，便于审核与观察）----


@router.get("/entities", response_model=list[PublicEntity])
async def list_entities(
    entity_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[PublicEntity]:
    return await entity_repository.list(session, entity_type=entity_type, status=status)


@router.get("/entities/duplicates", response_model=EntityDuplicatesResponse)
async def list_entity_duplicates(
    entity_type: str | None = Query(default=None),
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> EntityDuplicatesResponse:
    """疑似重复实体（形态相同 / 缩写子串）+ 仍是混合主名的实体，供管理员合并 / 规范。"""
    groups = await entity_repository.find_duplicate_groups(session, entity_type=entity_type)
    mixed = await entity_repository.find_mixed_names(session, entity_type=entity_type)
    return EntityDuplicatesResponse(
        groups=[
            DuplicateGroup(reason=reason, entities=[PublicEntity.model_validate(e) for e in members])
            for reason, members in groups
        ],
        mixed_names=[PublicEntity.model_validate(e) for e in mixed],
    )


@router.post("/entities/{entity_id}/merge", response_model=PublicEntity)
async def merge_entity(
    entity_id: str,
    payload: EntityMergeRequest,
    admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PublicEntity:
    """把当前实体并入目标实体：引用与别名迁移到目标，当前实体标记 merged（不物理删）。"""
    if entity_id == payload.target_id:
        raise AppError(400, "merge_self", "不能并入自身。")
    result = await entity_repository.merge_entities(
        session, source_id=entity_id, target_id=payload.target_id, reviewer_id=admin.id
    )
    if result is None:
        raise AppError(400, "merge_failed", "合并失败：实体不存在或类型不一致。")
    return result


@router.post("/entities/{entity_id}/rename", response_model=PublicEntity)
async def rename_entity(
    entity_id: str,
    payload: EntityRenameRequest,
    admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PublicEntity:
    """规范实体主名（旧名转别名）。若与同类型其他实体撞名，应改用「合并」。"""
    try:
        result = await entity_repository.rename_canonical(
            session, entity_id=entity_id, new_canonical=payload.canonical_name, reviewer_id=admin.id
        )
    except ValueError:
        raise AppError(409, "rename_target_exists", "已有同名实体，请改用「合并」。")
    if result is None:
        raise AppError(404, "entity_not_found", "实体不存在。")
    return result
