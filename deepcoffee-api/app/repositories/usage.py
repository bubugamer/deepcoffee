from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import AiUsageEvent


class AiUsageRepository:
    """统一 AI 调用次数：每次 brew_parse / brew_confirm / knowledge_ask 记一条。"""

    async def record(self, session: AsyncSession, *, user_id: str, action: str, trace_id: str | None = None) -> None:
        session.add(AiUsageEvent(user_id=user_id, action=action, trace_id=trace_id))
        await session.flush()

    async def count_for(self, session: AsyncSession, user_id: str) -> int:
        result = await session.execute(
            select(func.count()).select_from(AiUsageEvent).where(AiUsageEvent.user_id == user_id)
        )
        return int(result.scalar_one())


ai_usage_repository = AiUsageRepository()
