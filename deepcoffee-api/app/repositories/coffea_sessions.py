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
        """续接本人已有会话；否则新建（含传了未知 / 他人 session_id 的情况）。"""
        if session_id:
            existing = await self.get(session, user_id=user_id, session_id=session_id)
            if existing is not None:
                return existing
        cs = CoffeaSession(
            session_id=f"sess_{uuid4().hex[:16]}",
            user_id=user_id,
            state={},
            recent_messages=[],
        )
        session.add(cs)
        await session.flush()
        return cs

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
    ) -> None:
        """追加一轮消息（含 assistant 的 results 摘要与时间戳），供跨设备同步回看。

        图片 / 草稿等交互态与大字段由调用方在传入前剥离。
        """
        turns = list(cs.recent_messages or [])
        turn: dict[str, Any] = {"role": role, "content": content or ""}
        if results:
            turn["results"] = results
        if at is not None:
            turn["at"] = at
        turns.append(turn)
        cs.recent_messages = turns[-self._MAX_TURNS :]


coffea_session_repository = CoffeaSessionRepository()
