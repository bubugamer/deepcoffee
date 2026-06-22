from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.tables import InviteCode, UserAiQuotaSetting, UserProfile as UserProfileORM
from app.repositories.usage import ai_usage_repository, current_month_window
from app.schemas.auth import AdminUserInfo, UserProfile, UserQuota
from app.services.entitlements import normalize_plan, plan_definitions, quota_for_plan


def quota_total_for(plan: str, settings: Settings, custom_limit: int | None = None) -> int | None:
    """每月 AI 问答次数上限。保留返回类型兼容旧调用，正常套餐均为有限次数。"""
    return quota_for_plan(plan, settings, custom_limit)


def _quota_features(plan: str, settings: Settings, total: int | None) -> list[str]:
    definition = plan_definitions(settings)[normalize_plan(plan)]
    if total != definition.monthly_quota:
        return [f"AI 问答 {total} 次 / 月", "自定义月额度"]
    return list(definition.features)


def _to_schema(row: UserProfileORM) -> UserProfile:
    return UserProfile(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        plan=normalize_plan(row.plan),
        role=row.role,
        status=row.status,
        timezone=row.timezone,
        unit_system=row.unit_system,
        created_at=row.created_at,
    )


class ProfileRepository:
    async def get_or_create(self, session: AsyncSession, user_id: str, email: str | None = None) -> UserProfile:
        row = await session.get(UserProfileORM, user_id)
        if row is None:
            display_name = email.split("@", 1)[0] if email else None
            row = UserProfileORM(id=user_id, email=email, display_name=display_name)
            session.add(row)
            await session.flush()
            await session.refresh(row)
        elif email and row.email != email:
            row.email = email
            await session.flush()
        return _to_schema(row)

    async def update(
        self,
        session: AsyncSession,
        user_id: str,
        *,
        display_name: str | None = None,
        timezone: str | None = None,
        unit_system: str | None = None,
    ) -> UserProfile:
        row = await session.get(UserProfileORM, user_id)
        if row is None:
            row = UserProfileORM(id=user_id)
            session.add(row)
        if display_name is not None:
            row.display_name = display_name
        if timezone is not None:
            row.timezone = timezone
        if unit_system is not None:
            row.unit_system = unit_system
        await session.flush()
        await session.refresh(row)
        return _to_schema(row)

    async def set_role(self, session: AsyncSession, user_id: str, role: str) -> None:
        row = await session.get(UserProfileORM, user_id)
        if row is None:
            raise AppError(404, "user_not_found", "User profile not found.")
        row.role = role
        await session.flush()

    async def quota_for(self, session: AsyncSession, user_id: str, settings: Settings) -> UserQuota:
        row = await session.get(UserProfileORM, user_id)
        plan = normalize_plan(row.plan if row is not None else "basic")
        quota_setting = await session.get(UserAiQuotaSetting, user_id)
        custom_limit = quota_setting.monthly_limit if quota_setting is not None else None
        total = quota_total_for(plan, settings, custom_limit)
        _, reset_at = current_month_window()
        used = await ai_usage_repository.effective_count_for(session, user_id)
        remaining = max(0, total - used)
        return UserQuota(
            plan=plan,
            balance=0,
            ai_used=used,
            ai_total=total,
            ai_remaining=remaining,
            reset_at=reset_at,
            features=_quota_features(plan, settings, total),
        )

    async def list_users_with_invites(
        self, session: AsyncSession, *, settings: Settings, page: int = 1, page_size: int = 20
    ) -> list[AdminUserInfo]:
        """管理员用户列表：每个注册用户 + 其绑定的邀请码（LEFT JOIN invite_codes.used_by）。"""
        offset = (page - 1) * page_size
        result = await session.execute(
            select(UserProfileORM, InviteCode.code, InviteCode.used_at)
            .outerjoin(InviteCode, InviteCode.used_by == UserProfileORM.id)
            .order_by(UserProfileORM.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        users: list[AdminUserInfo] = []
        for row, code, used_at in result.all():
            users.append(
                await self.admin_user_info(session, row, settings=settings, invite_code=code, invited_at=used_at)
            )
        return users

    async def admin_user_info(
        self,
        session: AsyncSession,
        row: UserProfileORM,
        *,
        settings: Settings,
        invite_code: str | None = None,
        invited_at: datetime | None = None,
    ) -> AdminUserInfo:
        quota_setting = await session.get(UserAiQuotaSetting, row.id)
        custom_limit = quota_setting.monthly_limit if quota_setting is not None else None
        total = quota_total_for(row.plan, settings, custom_limit)
        used = await ai_usage_repository.effective_count_for(session, row.id)
        remaining = max(0, total - used)
        return AdminUserInfo(
            id=row.id,
            email=row.email,
            display_name=row.display_name,
            plan=normalize_plan(row.plan),
            role=row.role,
            status=row.status,
            created_at=row.created_at,
            invite_code=invite_code,
            invited_at=invited_at,
            ai_used=used,
            ai_total=total,
            ai_remaining=remaining,
            quota_custom=custom_limit is not None,
        )

    async def set_quota(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        monthly_limit: int | None,
        actor_id: str | None,
        reason: str | None = None,
    ) -> None:
        row = await session.get(UserProfileORM, user_id)
        if row is None:
            raise AppError(404, "user_not_found", "User profile not found.")
        setting = await session.get(UserAiQuotaSetting, user_id)
        if setting is None:
            setting = UserAiQuotaSetting(user_id=user_id)
            session.add(setting)
        setting.monthly_limit = monthly_limit
        setting.updated_by = actor_id
        setting.reason = reason
        setting.updated_at = datetime.now(timezone.utc)
        await session.flush()

    async def assert_ai_quota(self, session: AsyncSession, user_id: str, *, settings: Settings) -> None:
        """AI 调用前的次数门禁：当前套餐月额度用满即 402。

        只读（查 plan + 计数），不建档也不写记录——profile 缺失视为 basic，由下游 handler 负责建档。
        """
        row = await session.get(UserProfileORM, user_id)
        plan = normalize_plan(row.plan if row is not None else "basic")
        quota_setting = await session.get(UserAiQuotaSetting, user_id)
        custom_limit = quota_setting.monthly_limit if quota_setting is not None else None
        total = quota_total_for(plan, settings, custom_limit)
        used = await ai_usage_repository.effective_count_for(session, user_id)
        if used >= total:
            raise AppError(
                402,
                "ai_quota_exceeded",
                "本月 AI 问答次数已用完，升级会员可获得更高额度。",
            )


profile_repository = ProfileRepository()
