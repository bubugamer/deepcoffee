"""用户长期记忆（L3 画像）读写。

只读写当前用户自己的记忆条目。抽取服务按 (kind, 归一化 content) 去重 upsert；
用户可在「我的口味档案」编辑 / 删除（删除置 dismissed，不物理删，避免抽取反复加回）。
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import UserMemory


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


class UserMemoryRepository:
    async def _all_for_user(self, session: AsyncSession, user_id: str) -> list[UserMemory]:
        result = await session.execute(select(UserMemory).where(UserMemory.user_id == user_id))
        return list(result.scalars().all())

    async def list_active(self, session: AsyncSession, user_id: str) -> list[UserMemory]:
        result = await session.execute(
            select(UserMemory)
            .where(UserMemory.user_id == user_id, UserMemory.status == "active")
            .order_by(UserMemory.kind, UserMemory.created_at)
        )
        return list(result.scalars().all())

    async def get(self, session: AsyncSession, *, user_id: str, memory_id: str) -> UserMemory | None:
        m = await session.get(UserMemory, memory_id)
        if m is None or m.user_id != user_id:
            return None
        return m

    async def upsert(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        kind: str,
        content: str,
        confidence: float = 0.6,
        source: str | None = None,
        source_ref: str | None = None,
    ) -> UserMemory:
        """按 (kind, 归一化 content) 去重：命中 active 则更新 confidence/来源；命中 dismissed 则不复活、不新建；否则新建。"""
        for m in await self._all_for_user(session, user_id):
            if m.kind == kind and _norm(m.content) == _norm(content):
                if m.status == "dismissed":
                    return m  # 用户删过这条，尊重其选择，不复活也不新建
                if confidence > m.confidence:
                    m.confidence = confidence
                if source:
                    m.source = source
                    m.source_ref = source_ref
                await session.flush()
                return m
        m = UserMemory(
            id=f"mem_{uuid4().hex[:16]}",
            user_id=user_id,
            kind=kind,
            content=content,
            confidence=confidence,
            source=source,
            source_ref=source_ref,
        )
        session.add(m)
        await session.flush()
        return m

    async def update_content(
        self, session: AsyncSession, *, user_id: str, memory_id: str, content: str
    ) -> UserMemory | None:
        """用户编辑记忆内容（确认过的事实，置高置信）。"""
        m = await self.get(session, user_id=user_id, memory_id=memory_id)
        if m is None:
            return None
        m.content = content
        m.confidence = 1.0
        await session.flush()
        return m

    async def dismiss(self, session: AsyncSession, *, user_id: str, memory_id: str) -> bool:
        """用户删除：置 dismissed（不物理删）。"""
        m = await self.get(session, user_id=user_id, memory_id=memory_id)
        if m is None:
            return False
        m.status = "dismissed"
        await session.flush()
        return True


user_memory_repository = UserMemoryRepository()
