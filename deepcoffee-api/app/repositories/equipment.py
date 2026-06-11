"""用户器具资料读写（bean_recommend_params 多轮闭环用）。

只读写当前用户自己的器具；completed 时按 (brew_method, grinder, filter_media) 去重保存，
避免每轮重复建一套。
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import UserEquipmentProfile


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


class EquipmentRepository:
    async def list_for_user(self, session: AsyncSession, user_id: str) -> list[UserEquipmentProfile]:
        result = await session.execute(
            select(UserEquipmentProfile)
            .where(UserEquipmentProfile.user_id == user_id)
            .order_by(UserEquipmentProfile.created_at)
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        brew_method: str | None,
        grinder: str | None,
        filter_media: str | None,
        water: str | None = None,
        label: str | None = None,
    ) -> UserEquipmentProfile:
        """按 (brew_method, grinder, filter_media) 去重：命中则更新 water/label，否则新建。"""
        existing = await self.list_for_user(session, user_id)
        key = (_norm(brew_method), _norm(grinder), _norm(filter_media))
        for profile in existing:
            if (_norm(profile.brew_method), _norm(profile.grinder), _norm(profile.filter_media)) == key:
                if water:
                    profile.water = water
                if label:
                    profile.label = label
                await session.flush()
                return profile
        profile = UserEquipmentProfile(
            id=f"eq_{uuid4().hex[:16]}",
            user_id=user_id,
            brew_method=brew_method,
            grinder=grinder,
            filter_media=filter_media,
            water=water,
            label=label,
            # 用户第一套器具自动设为默认；后续新增不抢默认。
            is_default=not existing,
        )
        session.add(profile)
        await session.flush()
        return profile

    async def set_default(self, session: AsyncSession, *, user_id: str, equipment_id: str) -> None:
        """把指定器具置为默认，其余全部取消（单默认不变量）。"""
        for profile in await self.list_for_user(session, user_id):
            profile.is_default = profile.id == equipment_id
        await session.flush()


equipment_repository = EquipmentRepository()
