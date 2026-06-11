"""管理员对用户修改的审计记录（admin_audit_events）。

记录在 admin 端点（套餐/角色/状态/额度调整），查询给「修改历史」弹窗用。
只在值真实变化时落记录，由调用方判定。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import AdminAuditEvent, UserProfile


class AdminAuditRepository:
    async def record(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        actor_id: str | None,
        action: str,
        before: str | None,
        after: str | None,
        reason: str | None = None,
    ) -> None:
        session.add(
            AdminAuditEvent(
                user_id=user_id,
                actor_id=actor_id,
                action=action,
                before_value=before,
                after_value=after,
                reason=reason,
            )
        )
        await session.flush()

    async def list_for_user(
        self,
        session: AsyncSession,
        user_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> list[tuple[AdminAuditEvent, str | None]]:
        """返回 (事件, 操作人邮箱) 列表，按时间倒序。actor 被删时邮箱为 None。"""
        result = await session.execute(
            select(AdminAuditEvent, UserProfile.email)
            .outerjoin(UserProfile, UserProfile.id == AdminAuditEvent.actor_id)
            .where(AdminAuditEvent.user_id == user_id)
            .order_by(AdminAuditEvent.created_at.desc(), AdminAuditEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [(event, email) for event, email in result.all()]


admin_audit_repository = AdminAuditRepository()
