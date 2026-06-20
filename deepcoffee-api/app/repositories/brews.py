from __future__ import annotations

from datetime import date
from uuid import uuid4

from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import BrewRecord as BrewRecordORM
from app.models.tables import UserBeanCard as UserBeanCardORM
from app.schemas.brew import BrewDraft, BrewEvaluation, BrewRecord, BrewRecordUpdateRequest
from app.services.brew_validation import format_ratio


def _draft_columns(draft: BrewDraft) -> dict:
    """Draft 的字段映射成 ORM 列值（嵌套模型转成 JSON 友好的 dict/list）。"""
    return {
        "bean_name": draft.bean_name,
        "origin": draft.origin,
        "roaster": draft.roaster,
        "process": draft.process,
        "varietal": draft.varietal,
        "brew_method": draft.brew_method,
        "device": draft.device,
        "grinder": draft.grinder,
        "grind_setting": draft.grind_setting,
        "filter_media": draft.filter_media,
        "water": draft.water,
        "dose_g": draft.dose_g,
        "water_ml": draft.water_ml,
        "water_temp_c": draft.water_temp_c,
        "ratio": draft.ratio,
        "ratio_value": draft.ratio_value,
        "brew_time": draft.brew_time,
        "brew_time_seconds": draft.brew_time_seconds,
        "brew_steps": [step.model_dump() for step in draft.brew_steps],
        "evaluation": draft.evaluation.model_dump() if draft.evaluation else None,
        "notes": draft.notes,
    }


def _rating_model(value: dict | None) -> BrewEvaluation | None:
    if not value:
        return None
    return BrewEvaluation.model_validate(value)


def _to_record(row: BrewRecordORM, bean_rating: dict | None = None) -> BrewRecord:
    record = BrewRecord.model_validate(row)
    record.bean_rating = _rating_model(bean_rating)
    return record


def _apply_ratio_from_amounts(updates: dict, row: BrewRecordORM) -> None:
    dose_g = updates.get("dose_g", row.dose_g)
    water_ml = updates.get("water_ml", row.water_ml)
    if dose_g is not None and water_ml is not None:
        ratio_value = round(float(water_ml) / float(dose_g), 2)
        updates["ratio_value"] = ratio_value
        updates["ratio"] = format_ratio(ratio_value)
    else:
        updates["ratio_value"] = None
        updates["ratio"] = None


class BrewRecordRepository:
    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        draft: BrewDraft,
        source_type: str,
        raw_input: str | None,
        recap: str,
        suggestions: list[str],
        trace_id: str,
        bean_card_id: str | None = None,
        brew_score: int | None = None,
        record_type: str = "user",
        is_user_visible: bool = True,
    ) -> BrewRecord:
        record = BrewRecordORM(
            id=f"brew_{uuid4().hex[:12]}",
            user_id=user_id,
            bean_card_id=bean_card_id,
            record_type=record_type,
            is_user_visible=is_user_visible,
            source_type=source_type,
            raw_input=raw_input,
            recap=recap,
            suggestions=suggestions,
            trace_id=trace_id,
            brew_score=brew_score,
            **_draft_columns(draft),
        )
        session.add(record)
        await session.flush()
        await session.refresh(record)
        rating = None
        if record.bean_card_id:
            card = await session.get(UserBeanCardORM, record.bean_card_id)
            rating = card.rating if card else None
        return _to_record(record, rating)

    async def list(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        page: int,
        page_size: int,
        q: str | None = None,
        bean: str | None = None,
        device: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[list[BrewRecord], int]:
        # 只列用户可见记录：official_suggestion / ai_suggestion（建议参数载体）不进列表。
        conditions = [BrewRecordORM.user_id == user_id, BrewRecordORM.is_user_visible.is_(True)]
        if q:
            like = f"%{q.strip()}%"
            conditions.append(
                or_(
                    BrewRecordORM.bean_name.ilike(like),
                    BrewRecordORM.origin.ilike(like),
                    BrewRecordORM.roaster.ilike(like),
                    BrewRecordORM.varietal.ilike(like),
                    BrewRecordORM.brew_method.ilike(like),
                    BrewRecordORM.device.ilike(like),
                    BrewRecordORM.grinder.ilike(like),
                    BrewRecordORM.filter_media.ilike(like),
                    BrewRecordORM.water.ilike(like),
                    BrewRecordORM.notes.ilike(like),
                    BrewRecordORM.raw_input.ilike(like),
                )
            )
        if bean:
            conditions.append(BrewRecordORM.bean_name.ilike(f"%{bean}%"))
        if device:
            conditions.append(BrewRecordORM.device.ilike(f"%{device}%"))
        if date_from:
            conditions.append(cast(BrewRecordORM.created_at, Date) >= date.fromisoformat(date_from))
        if date_to:
            conditions.append(cast(BrewRecordORM.created_at, Date) <= date.fromisoformat(date_to))

        total = int(
            (await session.execute(select(func.count()).select_from(BrewRecordORM).where(*conditions))).scalar_one()
        )
        result = await session.execute(
            select(BrewRecordORM)
            .where(*conditions)
            .order_by(BrewRecordORM.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list(result.scalars().all())
        ratings: dict[str, dict | None] = {}
        bean_ids = {row.bean_card_id for row in rows if row.bean_card_id}
        if bean_ids:
            cards = await session.execute(select(UserBeanCardORM.id, UserBeanCardORM.rating).where(UserBeanCardORM.id.in_(bean_ids)))
            ratings = {bean_id: rating for bean_id, rating in cards.all()}
        items = [_to_record(row, ratings.get(row.bean_card_id) if row.bean_card_id else None) for row in rows]
        return items, total

    async def get(self, session: AsyncSession, *, user_id: str, record_id: str) -> BrewRecord | None:
        row = await session.get(BrewRecordORM, record_id)
        if row is None or row.user_id != user_id:
            return None
        rating = None
        if row.bean_card_id:
            card = await session.get(UserBeanCardORM, row.bean_card_id)
            rating = card.rating if card else None
        return _to_record(row, rating)

    async def update(
        self, session: AsyncSession, *, user_id: str, record_id: str, payload: BrewRecordUpdateRequest
    ) -> BrewRecord | None:
        row = await session.get(BrewRecordORM, record_id)
        if row is None or row.user_id != user_id:
            return None

        has_bean_rating_update = "bean_rating" in payload.model_fields_set
        updates = payload.model_dump(exclude_unset=True)
        bean_rating = updates.pop("bean_rating", None)
        next_bean_card_id = updates.pop("bean_card_id", None)
        if next_bean_card_id is not None and row.bean_card_id is None:
            card = await session.get(UserBeanCardORM, next_bean_card_id)
            if card is not None and card.user_id == user_id and card.status == "active":
                row.bean_card_id = card.id
                row.bean_name = card.name
                row.origin = card.origin_name
                row.roaster = card.roaster_name
                row.process = card.process_name
                row.varietal = "、".join(card.varietal_names or []) or None
        if "brew_steps" in updates:
            updates["brew_steps"] = [step.model_dump() for step in (payload.brew_steps or [])]
        if "evaluation" in updates:
            updates["evaluation"] = payload.evaluation.model_dump() if payload.evaluation else None
        if has_bean_rating_update and row.bean_card_id:
            card = await session.get(UserBeanCardORM, row.bean_card_id)
            if card is not None and card.user_id == user_id:
                card.rating = payload.bean_rating.model_dump() if payload.bean_rating else None

        if {"dose_g", "water_ml"} & set(updates):
            _apply_ratio_from_amounts(updates, row)

        for key, value in updates.items():
            setattr(row, key, value)
        await session.flush()
        await session.refresh(row)
        rating = None
        if row.bean_card_id:
            card = await session.get(UserBeanCardORM, row.bean_card_id)
            rating = card.rating if card else None
        return _to_record(row, rating)

    async def delete(self, session: AsyncSession, *, user_id: str, record_id: str) -> bool:
        row = await session.get(BrewRecordORM, record_id)
        if row is None or row.user_id != user_id:
            return False
        await session.delete(row)
        await session.flush()
        return True

    async def compare(
        self, session: AsyncSession, *, user_id: str, record_ids: list[str] | None, bean_name: str | None
    ) -> list[BrewRecord]:
        if record_ids:
            conditions = [BrewRecordORM.user_id == user_id, BrewRecordORM.id.in_(record_ids)]
        elif bean_name:
            conditions = [
                BrewRecordORM.user_id == user_id,
                BrewRecordORM.is_user_visible.is_(True),
                BrewRecordORM.bean_name.ilike(f"%{bean_name}%"),
            ]
        else:
            return []
        result = await session.execute(
            select(BrewRecordORM).where(*conditions).order_by(BrewRecordORM.created_at.desc())
        )
        rows = list(result.scalars().all())
        ratings: dict[str, dict | None] = {}
        bean_ids = {row.bean_card_id for row in rows if row.bean_card_id}
        if bean_ids:
            cards = await session.execute(select(UserBeanCardORM.id, UserBeanCardORM.rating).where(UserBeanCardORM.id.in_(bean_ids)))
            ratings = {bean_id: rating for bean_id, rating in cards.all()}
        return [_to_record(row, ratings.get(row.bean_card_id) if row.bean_card_id else None) for row in rows]


brew_record_repository = BrewRecordRepository()
