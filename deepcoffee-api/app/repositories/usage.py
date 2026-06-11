from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import AiUsageAdjustment, AiUsageEvent

APP_TZ = ZoneInfo("Asia/Shanghai")

# 计费口径：一条用户请求只计一次额度——只统计「入口动作」。
# coffea 链路里 coffea_dispatch 是入口；coffea_<能力>、coffea_bean_autosave 等是同一条
# 消息的执行明细（仅供分析），不计入月额度，否则用户发一条带图消息额度会一次跳 2-3。
_BILLABLE_FILTER = or_(
    AiUsageEvent.action == "coffea_dispatch",
    AiUsageEvent.action.not_like("coffea_%"),
)


def current_month_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    local_now = now.astimezone(APP_TZ) if now else datetime.now(APP_TZ)
    start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


class AiUsageRepository:
    """统一 AI 调用次数：真实调用事件 + 管理员当月调整。"""

    async def record(self, session: AsyncSession, *, user_id: str, action: str, trace_id: str | None = None) -> None:
        session.add(AiUsageEvent(user_id=user_id, action=action, trace_id=trace_id))
        await session.flush()

    async def count_for(
        self,
        session: AsyncSession,
        user_id: str,
        *,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> int:
        if period_start is None or period_end is None:
            period_start, period_end = current_month_window()
        result = await session.execute(
            select(func.count())
            .select_from(AiUsageEvent)
            .where(
                AiUsageEvent.user_id == user_id,
                AiUsageEvent.created_at >= period_start,
                AiUsageEvent.created_at < period_end,
                _BILLABLE_FILTER,
            )
        )
        return int(result.scalar_one())

    async def adjustment_total_for(
        self,
        session: AsyncSession,
        user_id: str,
        *,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> int:
        if period_start is None or period_end is None:
            period_start, period_end = current_month_window()
        result = await session.execute(
            select(func.coalesce(func.sum(AiUsageAdjustment.delta), 0)).where(
                AiUsageAdjustment.user_id == user_id,
                AiUsageAdjustment.period_start == period_start,
                AiUsageAdjustment.period_end == period_end,
            )
        )
        return int(result.scalar_one() or 0)

    async def effective_count_for(
        self,
        session: AsyncSession,
        user_id: str,
        *,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> int:
        if period_start is None or period_end is None:
            period_start, period_end = current_month_window()
        raw = await self.count_for(session, user_id, period_start=period_start, period_end=period_end)
        adjustment = await self.adjustment_total_for(
            session, user_id, period_start=period_start, period_end=period_end
        )
        return max(0, raw + adjustment)

    async def set_effective_count(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        used_this_month: int,
        actor_id: str | None,
        reason: str | None = None,
    ) -> None:
        period_start, period_end = current_month_window()
        current = await self.effective_count_for(
            session, user_id, period_start=period_start, period_end=period_end
        )
        delta = used_this_month - current
        if delta == 0:
            return
        session.add(
            AiUsageAdjustment(
                user_id=user_id,
                period_start=period_start,
                period_end=period_end,
                delta=delta,
                reason=reason,
                actor_id=actor_id,
            )
        )
        await session.flush()


ai_usage_repository = AiUsageRepository()
