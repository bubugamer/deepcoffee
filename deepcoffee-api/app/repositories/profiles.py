from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.tables import InviteCode, UserProfile as UserProfileORM
from app.repositories.usage import ai_usage_repository
from app.schemas.auth import AdminUserInfo, UserProfile, UserQuota


def quota_total_for(plan: str, settings: Settings) -> int | None:
    """每月 AI 问答次数上限：basic 取配置值，pro（及其它付费档）视为无限（None）。"""
    if plan == "basic":
        return settings.ai_quota_basic
    return None


def _quota_features(total: int | None) -> list[str]:
    ai_line = "AI 问答无限次" if total is None else f"AI 问答 {total} 次 / 月"
    return [
        "知识库文章免费浏览",
        ai_line,
        "冲煮记录不限条数，AI 录入消耗问答次数",
    ]


def _to_schema(row: UserProfileORM) -> UserProfile:
    return UserProfile(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        plan=row.plan,
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
        plan = row.plan if row is not None else "basic"
        total = quota_total_for(plan, settings)
        used = await ai_usage_repository.count_for(session, user_id)
        return UserQuota(
            plan=plan,
            balance=0,
            ai_used=used,
            ai_total=total,
            reset_at=None,
            features=_quota_features(total),
        )

    async def list_users_with_invites(
        self, session: AsyncSession, *, page: int = 1, page_size: int = 20
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
        return [
            AdminUserInfo(
                id=row.id,
                email=row.email,
                display_name=row.display_name,
                plan=row.plan,
                role=row.role,
                status=row.status,
                created_at=row.created_at,
                invite_code=code,
                invited_at=used_at,
            )
            for row, code, used_at in result.all()
        ]

    async def assert_ai_quota(self, session: AsyncSession, user_id: str, *, settings: Settings) -> None:
        """AI 调用前的次数门禁：basic 用满即 402；pro 无限放行。

        只读（查 plan + 计数），不建档也不写记录——profile 缺失视为 basic，由下游 handler 负责建档。
        """
        row = await session.get(UserProfileORM, user_id)
        plan = row.plan if row is not None else "basic"
        total = quota_total_for(plan, settings)
        if total is None:
            return
        used = await ai_usage_repository.count_for(session, user_id)
        if used >= total:
            raise AppError(
                402,
                "ai_quota_exceeded",
                "本月 AI 问答次数已用完，升级 Pro 可无限使用。",
            )


profile_repository = ProfileRepository()
