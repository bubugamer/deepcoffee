from __future__ import annotations

from datetime import date
from uuid import uuid4

from sqlalchemy import Date, Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import BrewRecord as BrewRecordORM
from app.models.tables import UserBeanCard as UserBeanCardORM
from app.schemas.brew import AnonymousBrewRecord, BrewDraft, BrewEvaluation, BrewRecord, BrewRecordUpdateRequest
from app.services.brew_validation import format_ratio


def _draft_columns(draft: BrewDraft) -> dict:
    """Draft 的字段映射成 ORM 列值（嵌套模型转成 JSON 友好的 dict/list）。

    豆名/产地/烘焙商/处理法/品种不再落库——它们随读取从关联豆卡现取（见 `_apply_card_fields`）。
    """
    return {
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


def _card_bean_fields(card: UserBeanCardORM | None) -> dict[str, str | None]:
    """从关联豆卡派生 bean_name/roaster/origin/process/varietal（产地/处理法/品种来自「豆源」
    bean_components：单豆取该条、拼配给汇总、无豆源留空）。单一真相＝豆卡，改名即时生效。"""
    if card is None:
        return {"bean_name": None, "roaster": None, "origin": None, "process": None, "varietal": None}
    comps = [c for c in (card.bean_components or []) if isinstance(c, dict)]
    if len(comps) == 1:
        c = comps[0]
        origin = c.get("origin_name")
        process = c.get("process_name")
        varietal = "、".join(c.get("varietal_names") or []) or None
    elif len(comps) >= 2:
        origin = "拼配 · 多产地"
        process = "多处理法"
        vs: list[str] = []
        for c in comps:
            for v in c.get("varietal_names") or []:
                if v and v not in vs:
                    vs.append(v)
        varietal = "、".join(vs) or None
    else:
        origin = process = varietal = None
    return {
        "bean_name": card.name,
        "roaster": card.roaster_name,
        "origin": origin,
        "process": process,
        "varietal": varietal,
    }


def _apply_card_fields(record: BrewRecord, card: UserBeanCardORM | None) -> None:
    if card is None:
        return
    fields = _card_bean_fields(card)
    record.bean_name = fields["bean_name"]
    record.roaster = fields["roaster"]
    record.origin = fields["origin"]
    record.process = fields["process"]
    record.varietal = fields["varietal"]


def _to_record(row: BrewRecordORM, card: UserBeanCardORM | None = None) -> BrewRecord:
    record = BrewRecord.model_validate(row)
    _apply_card_fields(record, card)
    record.bean_rating = _rating_model(card.rating if card is not None else None)
    return record


def _to_anonymous_record(row: BrewRecordORM, card: UserBeanCardORM | None = None) -> AnonymousBrewRecord:
    fields = _card_bean_fields(card)
    return AnonymousBrewRecord(
        id=row.id,
        bean_name=fields["bean_name"],
        origin=fields["origin"],
        roaster=fields["roaster"],
        process=fields["process"],
        varietal=fields["varietal"],
        brew_method=row.brew_method,
        device=row.device,
        grinder=row.grinder,
        grind_setting=row.grind_setting,
        filter_media=row.filter_media,
        water=row.water,
        dose_g=row.dose_g,
        water_ml=row.water_ml,
        water_temp_c=row.water_temp_c,
        ratio=row.ratio,
        ratio_value=row.ratio_value,
        brew_time=row.brew_time,
        brew_time_seconds=row.brew_time_seconds,
        brew_steps=row.brew_steps or [],
        evaluation=_rating_model(row.evaluation),
        brew_score=row.brew_score,
        created_at=row.created_at,
    )


async def _load_cards(session: AsyncSession, bean_ids: set[str]) -> dict[str, UserBeanCardORM]:
    """一次性把这批记录关联的豆卡捞出，按 id 索引（供 `_to_record` 派生豆名等字段）。"""
    ids = {bid for bid in bean_ids if bid}
    if not ids:
        return {}
    result = await session.execute(select(UserBeanCardORM).where(UserBeanCardORM.id.in_(ids)))
    return {card.id: card for card in result.scalars().all()}


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
        card = await session.get(UserBeanCardORM, record.bean_card_id) if record.bean_card_id else None
        return _to_record(record, card)

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
        # 每条记录都关联一张豆卡（bean_card_id NOT NULL），故内连豆卡表，豆名等按豆卡字段搜索/筛选。
        conditions = [BrewRecordORM.user_id == user_id, BrewRecordORM.is_user_visible.is_(True)]
        if q:
            like = f"%{q.strip()}%"
            conditions.append(
                or_(
                    UserBeanCardORM.name.ilike(like),
                    UserBeanCardORM.roaster_name.ilike(like),
                    cast(UserBeanCardORM.bean_components, Text).ilike(like),
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
            conditions.append(UserBeanCardORM.name.ilike(f"%{bean}%"))
        if device:
            conditions.append(BrewRecordORM.device.ilike(f"%{device}%"))
        if date_from:
            conditions.append(cast(BrewRecordORM.created_at, Date) >= date.fromisoformat(date_from))
        if date_to:
            conditions.append(cast(BrewRecordORM.created_at, Date) <= date.fromisoformat(date_to))

        join = (UserBeanCardORM, UserBeanCardORM.id == BrewRecordORM.bean_card_id)
        total = int(
            (
                await session.execute(
                    select(func.count()).select_from(BrewRecordORM).join(*join).where(*conditions)
                )
            ).scalar_one()
        )
        result = await session.execute(
            select(BrewRecordORM)
            .join(*join)
            .where(*conditions)
            .order_by(BrewRecordORM.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list(result.scalars().all())
        cards = await _load_cards(session, {row.bean_card_id for row in rows})
        items = [_to_record(row, cards.get(row.bean_card_id)) for row in rows]
        return items, total

    async def get(self, session: AsyncSession, *, user_id: str, record_id: str) -> BrewRecord | None:
        row = await session.get(BrewRecordORM, record_id)
        if row is None or row.user_id != user_id:
            return None
        card = await session.get(UserBeanCardORM, row.bean_card_id) if row.bean_card_id else None
        return _to_record(row, card)

    async def list_peer_for_bean(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        bean_card_id: str,
        limit: int = 50,
    ) -> list[AnonymousBrewRecord] | None:
        from app.repositories.beans import _same_bean_key  # 复用同豆键，避免模块级循环依赖

        source_card = await session.get(UserBeanCardORM, bean_card_id)
        if source_card is None or source_card.user_id != user_id or source_card.status != "active":
            return None

        # 身份过弱（无烘焙商，或没有任何带产地的豆源）不做同豆匹配，避免过度聚合。
        has_roaster = bool(source_card.roaster_entity_id or (source_card.roaster_name or "").strip())
        has_origin = any(
            isinstance(c, dict) and (c.get("origin_entity_id") or (c.get("origin_name") or "").strip())
            for c in (source_card.bean_components or [])
        )
        if not (has_roaster and has_origin):
            return []
        source_key = _same_bean_key(source_card)

        # 同豆判定与广场聚合同口径（_same_bean_key：烘焙商 + 豆名 + 豆源集合），在应用层比对。
        result = await session.execute(
            select(BrewRecordORM, UserBeanCardORM)
            .join(UserBeanCardORM, UserBeanCardORM.id == BrewRecordORM.bean_card_id)
            .where(
                BrewRecordORM.user_id != user_id,
                BrewRecordORM.record_type == "user",
                BrewRecordORM.is_user_visible.is_(True),
                UserBeanCardORM.status == "active",
            )
            .order_by(BrewRecordORM.created_at.desc())
        )
        out: list[AnonymousBrewRecord] = []
        for row, card in result.all():
            if _same_bean_key(card) == source_key:
                out.append(_to_anonymous_record(row, card))
                if len(out) >= limit:
                    break
        return out

    async def update(
        self, session: AsyncSession, *, user_id: str, record_id: str, payload: BrewRecordUpdateRequest
    ) -> BrewRecord | None:
        row = await session.get(BrewRecordORM, record_id)
        if row is None or row.user_id != user_id:
            return None

        has_bean_rating_update = "bean_rating" in payload.model_fields_set
        updates = payload.model_dump(exclude_unset=True)
        bean_rating = updates.pop("bean_rating", None)
        # 记录必关联豆卡（bean_card_id NOT NULL），不支持经 update 改挂豆卡：剥离该字段避免误改。
        updates.pop("bean_card_id", None)
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
        card = await session.get(UserBeanCardORM, row.bean_card_id) if row.bean_card_id else None
        return _to_record(row, card)

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
        join = (UserBeanCardORM, UserBeanCardORM.id == BrewRecordORM.bean_card_id)
        if record_ids:
            conditions = [BrewRecordORM.user_id == user_id, BrewRecordORM.id.in_(record_ids)]
        elif bean_name:
            conditions = [
                BrewRecordORM.user_id == user_id,
                BrewRecordORM.is_user_visible.is_(True),
                UserBeanCardORM.name.ilike(f"%{bean_name}%"),
            ]
        else:
            return []
        result = await session.execute(
            select(BrewRecordORM).join(*join).where(*conditions).order_by(BrewRecordORM.created_at.desc())
        )
        rows = list(result.scalars().all())
        cards = await _load_cards(session, {row.bean_card_id for row in rows})
        return [_to_record(row, cards.get(row.bean_card_id)) for row in rows]


brew_record_repository = BrewRecordRepository()
