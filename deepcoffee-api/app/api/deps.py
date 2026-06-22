from __future__ import annotations

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import AuthenticatedUser, get_current_user
from app.models.tables import InviteCode, UserProfile
from app.repositories.profiles import profile_repository


async def require_member(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    """业务接口的成员门禁：账号未被禁用，且已绑定邀请码（或是 admin）。

    挂在业务 router 的 dependencies 上。invite_required 是前端「补填邀请码」界面的触发信号；
    未建档用户（profile 缺失）同样走 invite_required——补码流程里 redeem 会先建档。
    """
    profile = await session.get(UserProfile, user.id)
    if profile is not None and profile.status == "disabled":
        raise AppError(403, "account_disabled", "账号已被禁用，如有疑问请联系管理员。")
    if not settings.enforce_invite_gate:
        return user
    if profile is not None and profile.role == "admin":
        return user
    if user.id in settings.admin_user_ids:
        return user
    bound = await session.scalar(
        select(func.count()).select_from(InviteCode).where(InviteCode.used_by == user.id)
    )
    if bound:
        return user
    raise AppError(403, "invite_required", "请先填写邀请码以激活账号。")


async def require_ai_quota(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> None:
    """AI 调用前的次数门禁依赖：按当前套餐月额度拦截。

    挂在路由装饰器的 dependencies 里即可，handler 函数签名/函数体无需改动。FastAPI 在单个
    请求内复用同一 get_session 依赖结果，门禁与 handler 用同一 session，计数一致。
    """
    await profile_repository.assert_ai_quota(session, user.id, settings=settings)
