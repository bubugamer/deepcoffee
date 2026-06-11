from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import AuthenticatedUser, require_admin
from app.models.tables import CandidateFact as CandidateFactORM
from app.models.tables import InviteCode, NewapiBillingLink, Proposal as ProposalORM, UserProfile
from app.repositories.candidates import candidate_repository
from app.repositories.entities import entity_repository
from sqlalchemy import func, select

from app.repositories.invites import InviteAlreadyUsedError, InviteRepository
from app.repositories.profiles import profile_repository
from app.schemas.auth import AdminStats, AdminUserInfo, AdminUserUpdateRequest, InviteCodeInfo, InviteCreateRequest
from app.schemas.candidate import CandidateFact, CandidatePromoteResponse, CandidateReviewRequest
from app.schemas.entity import PublicEntity
from app.schemas.proposal import Proposal, ProposalMarkAppliedRequest, ProposalReviewRequest
from app.services.candidate_service import candidate_service
from app.services.knowledge_service import KnowledgeService, get_knowledge_service
from app.services.billing_service import billing_service
from app.services.newapi_client import NewApiClient, NewApiError
from app.services.proposal_service import proposal_service

router = APIRouter(prefix="/admin", tags=["admin"])


def _new_api_user_already_missing(exc: NewApiError) -> bool:
    """判断 delete_user 失败是否等价于“远端用户本来就不存在”。

    repair 的核心保护是：只有远端删除成功，或能确认远端已经没有这个用户，才允许删本地 link。
    普通网络错误、鉴权错误、路由错误都不能被当作“已删除”，否则会把状态修得更乱。
    """
    message = (exc.message or "").lower()
    if "404 page not found" in message:
        return False
    missing_markers = (
        "user not found",
        "record not found",
        "no rows in result set",
        "用户不存在",
        "用户未找到",
        "未找到用户",
    )
    return any(marker in message for marker in missing_markers)


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
) -> AdminUserInfo:
    if payload.plan is None and payload.role is None and payload.status is None:
        raise AppError(400, "empty_update", "Provide at least one of plan / role / status.")
    profile = await session.get(UserProfile, user_id)
    if profile is None:
        raise AppError(404, "user_not_found", "User profile not found.")
    # 防自锁：管理员不能撤掉自己的 admin、也不能禁用自己（避免唯一管理员把自己关在门外）。
    if user_id == admin.id and (payload.role == "user" or payload.status == "disabled"):
        raise AppError(400, "cannot_modify_self", "不能对自己执行降级或禁用操作。")
    if payload.plan is not None:
        profile.plan = payload.plan
    if payload.role is not None:
        profile.role = payload.role
    if payload.status is not None:
        profile.status = payload.status
    await session.flush()
    await session.refresh(profile)
    return AdminUserInfo(
        id=profile.id,
        email=profile.email,
        display_name=profile.display_name,
        plan=profile.plan,
        role=profile.role,
        status=profile.status,
        created_at=profile.created_at,
    )


@router.get("/users", response_model=list[AdminUserInfo])
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AdminUserInfo]:
    return await profile_repository.list_users_with_invites(session, page=page, page_size=page_size)


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
    return items[start : start + page_size]


@router.get("/candidates/{candidate_id}", response_model=CandidateFact)
async def get_candidate(
    candidate_id: str,
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CandidateFact:
    row = await candidate_repository.get_orm(session, candidate_id)
    if row is None:
        raise AppError(404, "candidate_not_found", "Candidate fact not found.")
    return CandidateFact.model_validate(row)


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


@router.post("/billing-links/{user_id}/repair")
async def repair_billing_link(
    user_id: str,
    _admin: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str | bool | None]:
    """重建用户的 new-api 影子账户映射。

    new-api 未配置时直接 skipped，不改本地数据。已配置时，只有远端用户删除成功，
    或远端用户已不存在，才删除本地 link 并重建，避免 repair 把临时故障扩大成数据不一致。
    """
    if not billing_service.enabled:
        return {
            "status": "skipped",
            "reason": "new-api is not configured",
            "old_newapi_user_id": None,
            "newapi_user_id": None,
            "has_token": False,
        }

    profile = await session.get(UserProfile, user_id)
    if profile is None:
        raise AppError(404, "user_not_found", "User profile not found.")

    link = await session.get(NewapiBillingLink, user_id)
    old_newapi_user_id = link.newapi_user_id if link is not None else None
    if link is not None:
        try:
            await NewApiClient(billing_service.settings).delete_user(link.newapi_user_id)
        except NewApiError as exc:
            if not _new_api_user_already_missing(exc):
                raise AppError(
                    exc.status_code,
                    "new_api_delete_failed",
                    "Could not delete the existing new-api shadow user; local link was left unchanged.",
                    details={"newapi_user_id": link.newapi_user_id},
                ) from exc
        await session.delete(link)
        await session.flush()

    new_link = await billing_service.ensure_shadow_account(
        session, user_id=user_id, email=profile.email, plan=profile.plan
    )
    if new_link is None:
        raise AppError(502, "shadow_account_repair_failed", "Could not create a new shadow account.")

    return {
        "status": "repaired" if old_newapi_user_id is not None else "created",
        "reason": None,
        "old_newapi_user_id": old_newapi_user_id,
        "newapi_user_id": new_link.newapi_user_id,
        "has_token": bool(new_link.internal_token),
    }
