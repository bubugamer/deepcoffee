"""用户单件器具库存读写。

业务主表是 user_equipment_items；旧的 user_equipment_profiles 只保留作迁移/回滚观察。
"""

from __future__ import annotations

import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import UserEquipmentItem

EQUIPMENT_CATEGORIES = ("brewer", "grinder", "filter_media", "water")


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


class EquipmentRepository:
    async def list_for_user(self, session: AsyncSession, user_id: str) -> list[UserEquipmentItem]:
        result = await session.execute(
            select(UserEquipmentItem)
            .where(UserEquipmentItem.user_id == user_id)
            .order_by(UserEquipmentItem.category, UserEquipmentItem.is_default.desc(), UserEquipmentItem.created_at)
        )
        return list(result.scalars().all())

    async def list_by_category(
        self, session: AsyncSession, *, user_id: str, category: str
    ) -> list[UserEquipmentItem]:
        result = await session.execute(
            select(UserEquipmentItem)
            .where(UserEquipmentItem.user_id == user_id, UserEquipmentItem.category == category)
            .order_by(UserEquipmentItem.is_default.desc(), UserEquipmentItem.created_at)
        )
        return list(result.scalars().all())

    async def get_defaults(self, session: AsyncSession, user_id: str) -> dict[str, UserEquipmentItem]:
        items = await self.list_for_user(session, user_id)
        defaults: dict[str, UserEquipmentItem] = {}
        for item in items:
            if item.is_default and item.category not in defaults:
                defaults[item.category] = item
        return defaults

    async def find_by_name(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        category: str,
        name: str | None,
    ) -> UserEquipmentItem | None:
        normalized = _norm(name)
        if not normalized:
            return None
        result = await session.execute(
            select(UserEquipmentItem).where(
                UserEquipmentItem.user_id == user_id,
                UserEquipmentItem.category == category,
                UserEquipmentItem.normalized_name == normalized,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        category: str,
        name: str,
        notes: str | None = None,
        is_default: bool | None = None,
    ) -> UserEquipmentItem:
        cleaned = _clean(name)
        existing = await self.find_by_name(session, user_id=user_id, category=category, name=cleaned)
        if existing:
            if notes is not None:
                existing.notes = notes or None
            if is_default is True:
                await self.set_default(session, user_id=user_id, equipment_id=existing.id)
            elif is_default is False:
                existing.is_default = False
            await session.flush()
            return existing

        siblings = await self.list_by_category(session, user_id=user_id, category=category)
        should_default = is_default if is_default is not None else not siblings
        item = UserEquipmentItem(
            id=f"eqi_{uuid4().hex[:16]}",
            user_id=user_id,
            category=category,
            name=cleaned,
            normalized_name=_norm(cleaned),
            notes=notes or None,
            is_default=bool(should_default),
        )
        session.add(item)
        await session.flush()
        if item.is_default:
            await self.set_default(session, user_id=user_id, equipment_id=item.id)
        return item

    async def set_default(self, session: AsyncSession, *, user_id: str, equipment_id: str) -> None:
        item = await session.get(UserEquipmentItem, equipment_id)
        if item is None or item.user_id != user_id:
            return
        for sibling in await self.list_by_category(session, user_id=user_id, category=item.category):
            sibling.is_default = sibling.id == equipment_id
        await session.flush()


equipment_repository = EquipmentRepository()
