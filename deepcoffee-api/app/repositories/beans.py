from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import BrewRecord as BrewRecordORM
from app.models.tables import PublicEntity as PublicEntityORM
from app.models.tables import UserBeanCard as UserBeanCardORM
from app.repositories.entities import entity_repository
from app.schemas.bean import (
    Bean,
    BeanDraft,
    BeanFlavor,
    BeanRecommendedParams,
    BeanUpdateRequest,
    default_flavor,
)


def _record_to_params(row: BrewRecordORM) -> BeanRecommendedParams:
    return BeanRecommendedParams(
        record_id=row.id,
        record_type=row.record_type,
        device=row.device,
        grinder=row.grinder,
        grind_setting=row.grind_setting,
        dose_g=row.dose_g,
        water_ml=row.water_ml,
        water_temp_c=row.water_temp_c,
        ratio=row.ratio,
        ratio_value=row.ratio_value,
        brew_time_seconds=row.brew_time_seconds,
    )


def _overall_score(rating: dict | None) -> int | None:
    if not isinstance(rating, dict):
        return None
    overall = rating.get("overall")
    if isinstance(overall, dict):
        score = overall.get("score")
        if isinstance(score, (int, float)):
            return int(score)
    return None


def _clean_text(value: str | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _card_name(draft: BeanDraft) -> str:
    """豆卡主名称创建后保持稳定，优先使用豆袋正面 / 烘焙商产品名。"""

    return (
        _clean_text(draft.name)
        or _clean_text(draft.roaster_product_name)
        or _clean_text(draft.coffee_source_name)
        or "未命名豆子"
    )


class BeanRepository:
    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        draft: BeanDraft,
        source_type: str,
        raw_input: str | None,
        trace_id: str,
    ) -> str:
        flavor = draft.flavor or default_flavor()
        card = UserBeanCardORM(
            id=f"bean_{uuid4().hex[:12]}",
            user_id=user_id,
            source_type=source_type,
            raw_input=raw_input,
            name=_card_name(draft),
            roaster_name=draft.roaster_name,
            roaster_product_name=draft.roaster_product_name,
            coffee_source_name=draft.coffee_source_name,
            green_bean_merchant_name=draft.green_bean_merchant_name,
            green_bean_product_name=draft.green_bean_product_name,
            origin_name=draft.origin_name,
            process_name=draft.process_name,
            varietal_names=list(draft.varietal_names or []),
            altitude_text=draft.altitude_text,
            harvest_date_text=draft.harvest_date_text,
            roast_date_text=draft.roast_date_text,
            net_weight_text=draft.net_weight_text,
            bean_components=[component.model_dump(exclude_none=True) for component in draft.bean_components],
            flavor=flavor.model_dump(),
            private_notes=draft.private_notes,
            trace_id=trace_id,
        )
        session.add(card)
        await session.flush()
        await self._link_entities(session, card)
        await session.flush()
        return card.id

    async def _link_entities(self, session: AsyncSession, card: UserBeanCardORM) -> None:
        """把豆卡里的名称解析到公共实体，回填各 *_entity_id（命中 active 才填，否则清空）。

        消歧匹配（别名 / 形态）让「同一烘焙商不同写法」聚合到同一实体；解析失败不阻断建档。
        """
        mapping = [
            ("roaster", card.roaster_name, "roaster_entity_id"),
            ("origin", card.origin_name, "origin_entity_id"),
            ("process_method", card.process_name, "process_entity_id"),
            ("coffee_source", card.coffee_source_name, "coffee_source_entity_id"),
            ("green_bean_merchant", card.green_bean_merchant_name, "green_bean_merchant_entity_id"),
        ]
        for etype, name, attr in mapping:
            if not name:
                setattr(card, attr, None)
                continue
            try:
                ent = await entity_repository.resolve_entity(session, etype, name)
            except Exception:  # noqa: BLE001 — 关联失败不阻断建档/编辑
                ent = None
            setattr(card, attr, ent.id if (ent is not None and ent.status == "active") else None)

    async def _roaster_canonicals(
        self, session: AsyncSession, cards: list[UserBeanCardORM]
    ) -> dict[str, str]:
        """批量取豆卡所关联烘焙商实体的规范名（id → canonical_name），避免逐卡查询。"""
        ids = {c.roaster_entity_id for c in cards if c.roaster_entity_id}
        if not ids:
            return {}
        rows = await session.execute(
            select(PublicEntityORM.id, PublicEntityORM.canonical_name).where(PublicEntityORM.id.in_(ids))
        )
        return {row[0]: row[1] for row in rows.all()}

    # ---- 统计：用户可见的「user」冲煮记录数量。----
    async def _stats(self, session: AsyncSession, bean_ids: list[str]) -> dict[str, tuple[float | None, int]]:
        if not bean_ids:
            return {}
        result = await session.execute(
            select(BrewRecordORM.bean_card_id).where(
                BrewRecordORM.bean_card_id.in_(bean_ids),
                BrewRecordORM.record_type == "user",
                BrewRecordORM.is_user_visible.is_(True),
            )
        )
        counts: dict[str, int] = {bid: 0 for bid in bean_ids}
        for bean_id in result.scalars().all():
            counts[bean_id] = counts.get(bean_id, 0) + 1
        stats: dict[str, tuple[float | None, int]] = {}
        for bid in bean_ids:
            stats[bid] = (None, counts.get(bid, 0))
        return stats

    async def _recommended_params(
        self, session: AsyncSession, record_id: str | None
    ) -> BeanRecommendedParams | None:
        if not record_id:
            return None
        row = await session.get(BrewRecordORM, record_id)
        if row is None:
            return None
        return _record_to_params(row)

    def _to_bean(
        self,
        card: UserBeanCardORM,
        stats: tuple[float | None, int],
        rec_params: BeanRecommendedParams | None,
        roaster_canonical: str | None = None,
    ) -> Bean:
        _, record_count = stats
        rating = card.rating
        score = _overall_score(rating)
        return Bean(
            bean_id=card.id,
            name=card.name,
            roaster=card.roaster_name,
            roaster_entity_id=card.roaster_entity_id,
            roaster_canonical=roaster_canonical,
            roaster_product=card.roaster_product_name,
            coffee_source=card.coffee_source_name,
            green_bean_merchant=card.green_bean_merchant_name,
            green_bean_product=card.green_bean_product_name,
            origin=card.origin_name,
            process=card.process_name,
            varietal=list(card.varietal_names or []),
            altitude_text=card.altitude_text,
            harvest_date_text=card.harvest_date_text,
            roast_date_text=card.roast_date_text,
            net_weight_text=card.net_weight_text,
            bean_components=list(card.bean_components or []),
            flavor=BeanFlavor.model_validate(card.flavor or default_flavor().model_dump()),
            rating=rating,
            private_notes=card.private_notes,
            recommended_record_id=card.recommended_record_id,
            recommended_params=rec_params,
            avg_score=score,
            record_count=record_count,
            created_at=card.created_at,
            updated_at=card.updated_at,
        )

    async def _load_card(self, session: AsyncSession, user_id: str, bean_id: str) -> UserBeanCardORM | None:
        row = await session.get(UserBeanCardORM, bean_id)
        if row is None or row.user_id != user_id or row.status != "active":
            return None
        return row

    async def get(self, session: AsyncSession, *, user_id: str, bean_id: str) -> Bean | None:
        card = await self._load_card(session, user_id, bean_id)
        if card is None:
            return None
        stats = (await self._stats(session, [card.id]))[card.id]
        rec = await self._recommended_params(session, card.recommended_record_id)
        canon = await self._roaster_canonicals(session, [card])
        return self._to_bean(card, stats, rec, canon.get(card.roaster_entity_id))

    async def list(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        q: str | None = None,
        process: str | None = None,
        min_score: float | None = None,
    ) -> tuple[list[Bean], int]:
        conditions = [UserBeanCardORM.user_id == user_id, UserBeanCardORM.status == "active"]
        if q:
            like = f"%{q.strip()}%"
            name_conditions = [
                UserBeanCardORM.name.ilike(like),
                UserBeanCardORM.roaster_name.ilike(like),
                UserBeanCardORM.origin_name.ilike(like),
                UserBeanCardORM.process_name.ilike(like),
            ]
            # 消歧聚合：搜索词若能解析到某烘焙商实体，则把「回填了该实体」的豆卡一并纳入，
            # 让同一烘焙商的不同写法（coffee buff / Coffeebuff）一起被搜出。
            roaster_ent = await entity_repository.resolve_entity(session, "roaster", q.strip())
            if roaster_ent is not None:
                name_conditions.append(UserBeanCardORM.roaster_entity_id == roaster_ent.id)
            conditions.append(or_(*name_conditions))
        if process:
            conditions.append(UserBeanCardORM.process_name.ilike(f"%{process.strip()}%"))

        result = await session.execute(
            select(UserBeanCardORM).where(*conditions).order_by(UserBeanCardORM.created_at.desc())
        )
        cards = list(result.scalars().all())
        stats = await self._stats(session, [c.id for c in cards])
        canon = await self._roaster_canonicals(session, cards)
        beans: list[Bean] = []
        for card in cards:
            rec = await self._recommended_params(session, card.recommended_record_id)
            bean = self._to_bean(card, stats.get(card.id, (None, 0)), rec, canon.get(card.roaster_entity_id))
            if min_score is not None and (bean.avg_score is None or bean.avg_score < min_score):
                continue
            beans.append(bean)
        return beans, len(beans)

    async def update(
        self, session: AsyncSession, *, user_id: str, bean_id: str, payload: BeanUpdateRequest
    ) -> Bean | None:
        card = await self._load_card(session, user_id, bean_id)
        if card is None:
            return None
        updates = payload.model_dump(exclude_unset=True)
        if "flavor" in updates and payload.flavor is not None:
            updates["flavor"] = payload.flavor.model_dump()
        if "rating" in updates and payload.rating is not None:
            updates["rating"] = payload.rating.model_dump()
        if "varietal_names" in updates and payload.varietal_names is not None:
            updates["varietal_names"] = list(payload.varietal_names)
        if "bean_components" in updates and payload.bean_components is not None:
            updates["bean_components"] = [
                component.model_dump(exclude_none=True) for component in payload.bean_components
            ]
        for key, value in updates.items():
            setattr(card, key, value)
        await session.flush()
        await self._link_entities(session, card)
        await session.flush()
        await session.refresh(card)
        return await self.get(session, user_id=user_id, bean_id=bean_id)

    async def delete(self, session: AsyncSession, *, user_id: str, bean_id: str) -> bool:
        card = await self._load_card(session, user_id, bean_id)
        if card is None:
            return False
        card.status = "deleted"
        await session.flush()
        return True

    async def set_recommended_record(
        self, session: AsyncSession, *, user_id: str, bean_id: str, record_id: str
    ) -> Bean | None:
        card = await self._load_card(session, user_id, bean_id)
        if card is None:
            return None
        card.recommended_record_id = record_id
        await session.flush()
        await session.refresh(card)
        return await self.get(session, user_id=user_id, bean_id=bean_id)


bean_repository = BeanRepository()
