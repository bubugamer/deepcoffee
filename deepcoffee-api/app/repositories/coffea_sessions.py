"""Coffea 会话状态读写。统一一个 session_id 命名空间（见提示词清单 §0）。

只读写「当前用户自己的」会话：跨用户的 session_id 一律当作不存在，新建一个服务端 id，
避免 id 抢占 / 串号。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import CoffeaSession


class CoffeaSessionRepository:
    # 聊天历史保留最后 N 轮（recent_messages 同时承担跨设备同步的历史，存完整 turn）。
    _MAX_TURNS = 80

    async def get(self, session: AsyncSession, *, user_id: str, session_id: str) -> CoffeaSession | None:
        cs = await session.get(CoffeaSession, session_id)
        if cs is None or cs.user_id != user_id:
            return None
        return cs

    async def get_or_create(
        self, session: AsyncSession, *, user_id: str, session_id: str | None
    ) -> CoffeaSession:
        """续接本人已有会话；session_id 缺失 / 未知时回退到该用户的永久对话（与 GET /session 一致）。

        避免本地 session_id 丢失（如清浏览器缓存）后断成新会话、与历史割裂。
        """
        if session_id:
            existing = await self.get(session, user_id=user_id, session_id=session_id)
            if existing is not None:
                return existing
        # 没传 / 传了未知 / 他人 session_id：回退到该用户那条永久对话（没有才新建）。
        return await self.get_or_create_user_session(session, user_id=user_id)

    async def get_or_create_user_session(self, session: AsyncSession, *, user_id: str) -> CoffeaSession:
        """该用户那条「永久对话」：取最近活跃的一条；从无则新建。

        产品上 DeepCoffee AI 一个用户只有一条连续对话，不存在重置。跨设备同步即靠此。
        """
        result = await session.execute(
            select(CoffeaSession)
            .where(CoffeaSession.user_id == user_id)
            .order_by(CoffeaSession.updated_at.desc())
            .limit(1)
        )
        cs = result.scalar_one_or_none()
        if cs is not None:
            return cs
        cs = CoffeaSession(
            session_id=f"sess_{uuid4().hex[:16]}",
            user_id=user_id,
            state={},
            recent_messages=[],
        )
        session.add(cs)
        await session.flush()
        return cs

    def apply_state_updates(self, cs: CoffeaSession, updates: dict[str, Any] | None) -> None:
        """把调度器的 state_updates 合并进会话状态。

        只合并非空值（null 视为「本轮无更新」而非「清空」，保持 active 实体的连续性）。
        重新赋值整个 dict 以触发 SQLAlchemy 的变更检测。
        """
        if not isinstance(updates, dict) or not updates:
            return
        merged = dict(cs.state or {})
        changed = False
        for key, value in updates.items():
            if value is None:
                continue
            merged[key] = value
            changed = True
        if changed:
            cs.state = merged

    def append_turn(
        self,
        cs: CoffeaSession,
        role: str,
        content: str,
        *,
        results: list[dict[str, Any]] | None = None,
        at: int | None = None,
        images: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """追加一轮消息（含 assistant 的 results 摘要、时间戳、图片 URL），供跨设备同步回看。

        images 是图床公开 URL（图片本身存 Supabase Storage，不存 JSONB）；草稿等交互态在传入前剥离。
        返回因裁剪而被移出窗口的旧轮次（供 L2 摘要增量并入；未发生裁剪则空列表）。
        """
        turns = list(cs.recent_messages or [])
        turn: dict[str, Any] = {"role": role, "content": content or ""}
        if results:
            turn["results"] = results
        if at is not None:
            turn["at"] = at
        if images:
            turn["images"] = images
        turns.append(turn)
        if len(turns) > self._MAX_TURNS:
            dropped = turns[: len(turns) - self._MAX_TURNS]
            cs.recent_messages = turns[-self._MAX_TURNS :]
            return dropped
        cs.recent_messages = turns
        return []

    def set_summary(self, cs: CoffeaSession, summary: list[dict[str, Any]]) -> None:
        """整体替换会话摘要（摘要服务已做增量合并，这里只负责落库 / 触发变更检测）。"""
        cs.summary = list(summary)


coffea_session_repository = CoffeaSessionRepository()
