from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import InviteCode

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import AuthenticatedUser, get_current_user
from app.repositories.invites import InviteRepository
from app.repositories.profiles import profile_repository
from app.services.bootstrap import normalized_bootstrap_code
from app.services.billing_service import billing_service
from app.schemas.auth import (
    InviteRedeemRequest,
    InviteRedeemResponse,
    InviteValidateRequest,
    InviteValidateResponse,
    ProfileUpdateRequest,
    UserProfile,
    UserQuota,
)

router = APIRouter(tags=["auth"])


def get_invite_repository(settings: Settings = Depends(get_settings)) -> InviteRepository:
    return InviteRepository(default_codes={code.upper() for code in settings.default_invite_codes})


@router.post("/invites/validate", response_model=InviteValidateResponse)
async def validate_invite(
    payload: InviteValidateRequest,
    repository: InviteRepository = Depends(get_invite_repository),
    session: AsyncSession = Depends(get_session),
) -> InviteValidateResponse:
    valid = await repository.validate(session, payload.code)
    return InviteValidateResponse(
        valid=valid,
        message="Invite code is valid." if valid else "Invite code is invalid or already used.",
    )


@router.post("/invites/redeem", response_model=InviteRedeemResponse)
async def redeem_invite(
    payload: InviteRedeemRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repository: InviteRepository = Depends(get_invite_repository),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> InviteRedeemResponse:
    await profile_repository.get_or_create(session, user.id, user.email)
    redeemed = await repository.consume(session, payload.code, user.id)
    if not redeemed:
        raise AppError(400, "invite_invalid", "邀请码无效或已被使用。")
    # 初始化邀请码：消费它的注册者自动成为管理员（码本身一次性，且仅在系统
    # 尚无管理员时才会入库，见 services/bootstrap.py）。
    if payload.code.strip().upper() == normalized_bootstrap_code(settings):
        await profile_repository.set_role(session, user.id, "admin")
    return InviteRedeemResponse(redeemed=True, message="邀请码已使用。")


@router.get("/me", response_model=UserProfile)
async def get_me(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserProfile:
    await billing_service.sync_expired_membership(session, user.id)
    profile = await profile_repository.get_or_create(session, user.id, user.email)
    # 禁用账号在入口处拦截，前端据此展示「账号已禁用」而非正常应用。
    if profile.status == "disabled":
        raise AppError(403, "account_disabled", "账号已被禁用，如有疑问请联系管理员。")
    # invite_bound 与 require_member 的放行条件一致，供前端决定是否弹「补填邀请码」。
    settings = get_settings()
    if settings.enforce_invite_gate and profile.role != "admin" and user.id not in settings.admin_user_ids:
        bound = await session.scalar(
            select(func.count()).select_from(InviteCode).where(InviteCode.used_by == user.id)
        )
        profile.invite_bound = bool(bound)
    return profile


@router.patch("/me", response_model=UserProfile)
async def update_me(
    payload: ProfileUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserProfile:
    await profile_repository.get_or_create(session, user.id, user.email)
    return await profile_repository.update(
        session,
        user.id,
        display_name=payload.display_name,
        timezone=payload.timezone,
        unit_system=payload.unit_system,
    )


@router.get("/me/quota", response_model=UserQuota)
async def get_my_quota(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> UserQuota:
    await profile_repository.get_or_create(session, user.id, user.email)
    await billing_service.sync_expired_membership(session, user.id)
    return await profile_repository.quota_for(session, user.id, settings)
