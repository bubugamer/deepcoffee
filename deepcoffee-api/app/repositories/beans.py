from __future__ import annotations

from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import BrewRecord as BrewRecordORM
from app.models.tables import PublicEntity as PublicEntityORM
from app.models.tables import UserBeanCard as UserBeanCardORM
from app.repositories.entities import entity_repository, normalize_name
from app.schemas.bean import (
    Bean,
    BeanDraft,
    BeanFlavor,
    BeanRecommendedParams,
    BeanSquareImportItem,
    BeanSquareImportResponse,
    BeanSquareItem,
    BeanUpdateRequest,
    SquareComment,
    default_flavor,
)

# 豆子相关信息（产地/庄园/生豆商/生豆商产品/处理法/品种/海拔/采收期）一律入「豆源」bean_components：
# 单豆卡 1 条、拼配卡多条。顶层只留产品级（烘焙商/产品名/烘焙日期/净含量）。
_COMPONENT_TEXT_FIELDS = (
    "origin_name",
    "coffee_source_name",
    "green_bean_merchant_name",
    "green_bean_product_name",
    "process_name",
    "altitude_text",
    "harvest_date_text",
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


def _draft_components(draft: BeanDraft) -> list[dict]:
    """归一豆源：优先用 draft.bean_components；否则把顶层 per-bean 字段折成 1 条；都空则 []。"""
    if draft.bean_components:
        return [c.model_dump(exclude_none=True) for c in draft.bean_components]
    top = {
        "origin_name": _clean_text(draft.origin_name),
        "coffee_source_name": _clean_text(draft.coffee_source_name),
        "green_bean_merchant_name": _clean_text(draft.green_bean_merchant_name),
        "green_bean_product_name": _clean_text(draft.green_bean_product_name),
        "process_name": _clean_text(draft.process_name),
        "varietal_names": list(draft.varietal_names or []),
        "altitude_text": _clean_text(draft.altitude_text),
        "harvest_date_text": _clean_text(draft.harvest_date_text),
    }
    if not any(top.values()):
        return []
    return [{k: v for k, v in top.items() if v}]


def _product_type(components: list) -> str:
    return "blend" if len(components) >= 2 else "single"


def _component_key(comp: dict) -> tuple[str, str]:
    origin = comp.get("origin_entity_id") or normalize_name(comp.get("origin_name") or "")
    process = comp.get("process_entity_id") or normalize_name(comp.get("process_name") or "")
    return (origin, process)


def _same_bean_key(card: "UserBeanCardORM") -> tuple:
    """「同一支豆」分组键:烘焙商 + 归一豆名 + 豆源集合(各豆源的产地/处理法,实体 id 优先)。
    单豆=1 条豆源键、拼配=按豆源键排序的复合键 → 同款拼配自然归一,不同豆源不会误并。"""
    sources = tuple(sorted(_component_key(c) for c in (card.bean_components or [])))
    return (
        card.roaster_entity_id or normalize_name(card.roaster_name or ""),
        normalize_name(card.name or ""),
        sources,
    )


def _derive_top(card: "UserBeanCardORM") -> dict:
    """从豆源派生顶层展示字段:单豆取该条豆源、拼配标量留空(前端读 components/类型展示)、品种取并集便于搜索。"""
    comps = card.bean_components or []
    if len(comps) == 1:
        c = comps[0]
        return {
            "origin": c.get("origin_name"),
            "coffee_source": c.get("coffee_source_name"),
            "green_bean_merchant": c.get("green_bean_merchant_name"),
            "green_bean_product": c.get("green_bean_product_name"),
            "process": c.get("process_name"),
            "varietal": list(c.get("varietal_names") or []),
            "altitude_text": c.get("altitude_text"),
            "harvest_date_text": c.get("harvest_date_text"),
        }
    varietals: list[str] = []
    for c in comps:
        for v in c.get("varietal_names") or []:
            if v and v not in varietals:
                varietals.append(v)
    return {
        "origin": None,
        "coffee_source": None,
        "green_bean_merchant": None,
        "green_bean_product": None,
        "process": None,
        "varietal": varietals,
        "altitude_text": None,
        "harvest_date_text": None,
    }


def _card_name(draft: BeanDraft) -> str:
    """豆卡主名称创建后保持稳定，优先使用豆袋正面 / 烘焙商产品名。"""

    first_source = (draft.bean_components[0] if draft.bean_components else None)
    source_origin = _clean_text(first_source.coffee_source_name) if first_source else None
    return (
        _clean_text(draft.name)
        or _clean_text(draft.roaster_product_name)
        or _clean_text(draft.coffee_source_name)
        or source_origin
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
            roast_date_text=draft.roast_date_text,
            net_weight_text=draft.net_weight_text,
            bean_components=_draft_components(draft),
            flavor=flavor.model_dump(),
            private_notes=draft.private_notes,
            public_comment=draft.public_comment,
            trace_id=trace_id,
        )
        session.add(card)
        await session.flush()
        await self._link_entities(session, card)  # 逐豆源回填实体 id + 按条数写 bean_product_type
        await session.flush()
        return card.id

    async def _resolve_id(self, session: AsyncSession, etype: str, name: str | None) -> str | None:
        if not name or not str(name).strip():
            return None
        try:
            ent = await entity_repository.resolve_entity(session, etype, str(name).strip())
        except Exception:  # noqa: BLE001 — 关联失败不阻断建档/编辑
            return None
        return ent.id if (ent is not None and ent.status == "active") else None

    async def _link_entities(self, session: AsyncSession, card: UserBeanCardORM) -> None:
        """把豆卡名称解析到公共实体并回填:顶层 roaster/roaster_product,每条豆源 origin/process/coffee_source/
        green_bean_merchant/varietal。同时按豆源条数写 bean_product_type。解析失败不阻断建档/编辑。"""
        card.roaster_entity_id = await self._resolve_id(session, "roaster", card.roaster_name)
        # 产品实体(roaster_product)按「烘焙商作用域」解析:只连已审核通过的 active,绝不自动建。
        card.roaster_product_entity_id = None
        if card.roaster_product_name and card.roaster_entity_id:
            try:
                product = await entity_repository.resolve_roaster_product(
                    session, roaster_entity_id=card.roaster_entity_id, product_name=card.roaster_product_name
                )
            except Exception:  # noqa: BLE001
                product = None
            if product is not None and product.status == "active":
                card.roaster_product_entity_id = product.id

        new_components: list[dict] = []
        for comp in card.bean_components or []:
            if not isinstance(comp, dict):
                continue
            comp = dict(comp)
            comp["origin_entity_id"] = await self._resolve_id(session, "origin", comp.get("origin_name"))
            comp["process_entity_id"] = await self._resolve_id(session, "process_method", comp.get("process_name"))
            comp["coffee_source_entity_id"] = await self._resolve_id(session, "coffee_source", comp.get("coffee_source_name"))
            comp["green_bean_merchant_entity_id"] = await self._resolve_id(
                session, "green_bean_merchant", comp.get("green_bean_merchant_name")
            )
            vids: list[str] = []
            for v in comp.get("varietal_names") or []:
                vid = await self._resolve_id(session, "varietal", v)
                if vid:
                    vids.append(vid)
            comp["varietal_entity_ids"] = vids
            new_components.append(comp)
        card.bean_components = new_components  # 重新赋值以触发 JSONB 变更跟踪
        card.bean_product_type = _product_type(new_components)

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
        top = _derive_top(card)
        return Bean(
            bean_id=card.id,
            name=card.name,
            roaster=card.roaster_name,
            roaster_entity_id=card.roaster_entity_id,
            roaster_canonical=roaster_canonical,
            roaster_product=card.roaster_product_name,
            coffee_source=top["coffee_source"],
            green_bean_merchant=top["green_bean_merchant"],
            green_bean_product=top["green_bean_product"],
            origin=top["origin"],
            process=top["process"],
            varietal=top["varietal"],
            altitude_text=top["altitude_text"],
            harvest_date_text=top["harvest_date_text"],
            roast_date_text=card.roast_date_text,
            net_weight_text=card.net_weight_text,
            bean_components=list(card.bean_components or []),
            bean_product_type=card.bean_product_type or "single",
            flavor=BeanFlavor.model_validate(card.flavor or default_flavor().model_dump()),
            rating=rating,
            private_notes=card.private_notes,
            public_comment=card.public_comment,
            recommended_record_id=card.recommended_record_id,
            recommended_params=rec_params,
            avg_score=score,
            record_count=record_count,
            created_at=card.created_at,
            updated_at=card.updated_at,
        )

    def _to_square_item(
        self,
        card: UserBeanCardORM,
        stats: tuple[float | None, int],
        rec_params: BeanRecommendedParams | None,
        roaster_canonical: str | None = None,
    ) -> BeanSquareItem:
        _, record_count = stats
        rating = card.rating
        top = _derive_top(card)
        return BeanSquareItem(
            bean_id=card.id,
            name=card.name,
            roaster=card.roaster_name,
            roaster_canonical=roaster_canonical,
            roaster_product=card.roaster_product_name,
            coffee_source=top["coffee_source"],
            green_bean_merchant=top["green_bean_merchant"],
            green_bean_product=top["green_bean_product"],
            origin=top["origin"],
            process=top["process"],
            varietal=top["varietal"],
            altitude_text=top["altitude_text"],
            harvest_date_text=top["harvest_date_text"],
            roast_date_text=card.roast_date_text,
            net_weight_text=card.net_weight_text,
            bean_components=list(card.bean_components or []),
            bean_product_type=card.bean_product_type or "single",
            flavor=BeanFlavor.model_validate(card.flavor or default_flavor().model_dump()),
            rating=rating,
            public_comment=card.public_comment,
            recommended_params=rec_params,
            avg_score=_overall_score(rating),
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

    @staticmethod
    def _card_haystack(card: UserBeanCardORM) -> list[str]:
        hay = [card.name, card.roaster_name, card.roaster_product_name]
        for c in card.bean_components or []:
            if not isinstance(c, dict):
                continue
            hay += [
                c.get("origin_name"),
                c.get("coffee_source_name"),
                c.get("green_bean_merchant_name"),
                c.get("green_bean_product_name"),
                c.get("process_name"),
            ]
            hay += list(c.get("varietal_names") or [])
        return [h for h in hay if h]

    @staticmethod
    def _card_has_process(card: UserBeanCardORM, process: str) -> bool:
        pl = process.strip().lower()
        return any(
            isinstance(c, dict) and (c.get("process_name") or "").lower().find(pl) >= 0
            for c in card.bean_components or []
        )

    async def list(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        q: str | None = None,
        process: str | None = None,
        min_score: float | None = None,
    ) -> tuple[list[Bean], int]:
        # 豆名/产地等已归一到豆源(JSONB)：先按 user+status 取全量(单用户豆卡量小)，q/process 在 Python 侧匹配豆源。
        result = await session.execute(
            select(UserBeanCardORM)
            .where(UserBeanCardORM.user_id == user_id, UserBeanCardORM.status == "active")
            .order_by(UserBeanCardORM.created_at.desc())
        )
        cards = list(result.scalars().all())

        roaster_ent_id: str | None = None
        if q:
            ent = await entity_repository.resolve_entity(session, "roaster", q.strip())
            roaster_ent_id = ent.id if ent is not None else None

        def matches(card: UserBeanCardORM) -> bool:
            if q:
                ql = q.strip().lower()
                hit = any(ql in h.lower() for h in self._card_haystack(card))
                # 消歧聚合：搜索词解析到某烘焙商实体时，把回填了该实体的豆卡一并纳入。
                if not hit and not (roaster_ent_id and card.roaster_entity_id == roaster_ent_id):
                    return False
            if process and not self._card_has_process(card, process):
                return False
            return True

        cards = [c for c in cards if matches(c)]
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

    def _build_square_group(self, members, stats, canon, rec) -> tuple[BeanSquareItem, object]:
        """把「同豆」一组豆卡聚成一张广场条目:代表卡(组内最早)出结构化字段,
        再覆盖人气/总冲煮数/均分/评论聚合。返回 (条目, 组内最新时间) 供排序。"""
        members = sorted(members, key=lambda m: m.created_at)
        rep = members[0]
        item = self._to_square_item(rep, stats.get(rep.id, (None, 0)), rec, canon.get(rep.roaster_entity_id))
        item.owner_count = len({m.user_id for m in members})
        item.record_count = sum(stats.get(m.id, (None, 0))[1] for m in members)
        scores = [s for m in members if (s := _overall_score(m.rating)) is not None]
        item.avg_score = round(sum(scores) / len(scores), 1) if scores else None
        item.comments = sorted(
            (
                SquareComment(
                    comment=m.public_comment.strip(),
                    overall_score=_overall_score(m.rating),
                    created_at=m.created_at,
                )
                for m in members
                if m.public_comment and m.public_comment.strip()
            ),
            key=lambda c: c.created_at,
            reverse=True,
        )[:20]
        return item, max(m.created_at for m in members)

    @staticmethod
    def _square_text_match(item: BeanSquareItem, q: str) -> bool:
        ql = q.strip().lower()
        fields = [item.name, item.roaster, item.roaster_product, item.origin, item.process, item.public_comment]
        for c in item.bean_components or []:
            fields += [
                c.origin_name,
                c.coffee_source_name,
                c.green_bean_merchant_name,
                c.process_name,
            ]
            fields += list(c.varietal_names or [])
        return any(f and ql in f.lower() for f in fields)

    @staticmethod
    def _square_process_match(item: BeanSquareItem, process: str) -> bool:
        pl = process.strip().lower()
        if item.process and pl in item.process.lower():
            return True
        return any(c.process_name and pl in c.process_name.lower() for c in item.bean_components or [])

    async def list_square(
        self,
        session: AsyncSession,
        *,
        q: str | None = None,
        process: str | None = None,
    ) -> tuple[list[BeanSquareItem], int]:
        # 广场只展示「原创」豆卡(排除导入副本),并按「同豆」分组:同款只出一张代表卡 + 聚合人气/评分/评论。
        result = await session.execute(
            select(UserBeanCardORM).where(
                UserBeanCardORM.status == "active",
                UserBeanCardORM.source_bean_card_id.is_(None),
            )
        )
        cards = list(result.scalars().all())
        stats = await self._stats(session, [c.id for c in cards])
        canon = await self._roaster_canonicals(session, cards)

        groups: dict[tuple, list[UserBeanCardORM]] = {}
        for card in cards:
            groups.setdefault(_same_bean_key(card), []).append(card)

        built: list[tuple[BeanSquareItem, object]] = []
        for members in groups.values():
            rep = min(members, key=lambda m: m.created_at)
            rec = await self._recommended_params(session, rep.recommended_record_id)
            built.append(self._build_square_group(members, stats, canon, rec))

        # 搜索 / 筛选在聚合结果上做,保证 owner_count 计全组、不被搜索词截断。
        if q:
            built = [b for b in built if self._square_text_match(b[0], q)]
        if process:
            built = [b for b in built if self._square_process_match(b[0], process)]

        # 人气高在前,其次按组内最新时间。
        built.sort(key=lambda b: (b[0].owner_count, b[1]), reverse=True)
        items = [b[0] for b in built]
        return items, len(items)

    async def get_square(self, session: AsyncSession, *, bean_id: str) -> BeanSquareItem | None:
        card = await session.get(UserBeanCardORM, bean_id)
        # 副本（source_bean_card_id 不为空）不是广场条目：详情同样不暴露，保持与列表一致。
        if card is None or card.status != "active" or card.source_bean_card_id is not None:
            return None
        key = _same_bean_key(card)
        result = await session.execute(
            select(UserBeanCardORM).where(
                UserBeanCardORM.status == "active",
                UserBeanCardORM.source_bean_card_id.is_(None),
            )
        )
        members = [c for c in result.scalars().all() if _same_bean_key(c) == key] or [card]
        stats = await self._stats(session, [m.id for m in members])
        canon = await self._roaster_canonicals(session, members)
        rep = min(members, key=lambda m: m.created_at)
        rec = await self._recommended_params(session, rep.recommended_record_id)
        item, _ = self._build_square_group(members, stats, canon, rec)
        return item

    async def _existing_import(
        self, session: AsyncSession, *, user_id: str, source_bean_id: str
    ) -> UserBeanCardORM | None:
        result = await session.execute(
            select(UserBeanCardORM).where(
                UserBeanCardORM.user_id == user_id,
                UserBeanCardORM.source_bean_card_id == source_bean_id,
                UserBeanCardORM.status == "active",
            )
        )
        return result.scalars().first()

    async def _copy_recommended_record(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        source_record_id: str | None,
        target_bean_id: str,
        trace_id: str,
    ) -> str | None:
        if not source_record_id:
            return None
        source = await session.get(BrewRecordORM, source_record_id)
        if source is None:
            return None
        record = BrewRecordORM(
            id=f"brew_{uuid4().hex[:12]}",
            user_id=user_id,
            bean_card_id=target_bean_id,
            record_type="user_suggestion",
            is_user_visible=False,
            source_type="square_import",
            raw_input=None,
            brew_method=source.brew_method,
            device=source.device,
            grinder=source.grinder,
            grind_setting=source.grind_setting,
            filter_media=source.filter_media,
            water=source.water,
            dose_g=source.dose_g,
            water_ml=source.water_ml,
            water_temp_c=source.water_temp_c,
            ratio=source.ratio,
            ratio_value=source.ratio_value,
            brew_time=source.brew_time,
            brew_time_seconds=source.brew_time_seconds,
            brew_steps=[],
            evaluation=None,
            brew_score=None,
            notes=None,
            recap=None,
            suggestions=[],
            trace_id=trace_id,
        )
        session.add(record)
        await session.flush()
        return record.id

    async def import_from_square(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        source_bean_ids: list[str],
    ) -> BeanSquareImportResponse:
        items: list[BeanSquareImportItem] = []
        for source_id in dict.fromkeys(source_bean_ids):
            source = await session.get(UserBeanCardORM, source_id)
            if source is None or source.status != "active":
                continue
            if source.user_id == user_id:
                items.append(BeanSquareImportItem(source_bean_id=source.id, bean_id=source.id, status="existing"))
                continue
            existing = await self._existing_import(session, user_id=user_id, source_bean_id=source.id)
            if existing is not None:
                items.append(BeanSquareImportItem(source_bean_id=source.id, bean_id=existing.id, status="existing"))
                continue

            trace_id = f"bean_square_import_{uuid4().hex[:12]}"
            card = UserBeanCardORM(
                id=f"bean_{uuid4().hex[:12]}",
                user_id=user_id,
                source_type="square_import",
                raw_input=None,
                name=source.name,
                roaster_name=source.roaster_name,
                roaster_product_name=source.roaster_product_name,
                roast_date_text=source.roast_date_text,
                net_weight_text=source.net_weight_text,
                bean_components=list(source.bean_components or []),
                bean_product_type=source.bean_product_type or "single",
                roaster_entity_id=source.roaster_entity_id,
                roaster_product_entity_id=source.roaster_product_entity_id,
                flavor=dict(source.flavor or default_flavor().model_dump()),
                rating=source.rating,
                private_notes=None,
                public_comment=None,
                recommended_record_id=None,
                source_bean_card_id=source.id,
                trace_id=trace_id,
            )
            session.add(card)
            await session.flush()
            copied_record_id = await self._copy_recommended_record(
                session,
                user_id=user_id,
                source_record_id=source.recommended_record_id,
                target_bean_id=card.id,
                trace_id=trace_id,
            )
            card.recommended_record_id = copied_record_id
            await session.flush()
            items.append(BeanSquareImportItem(source_bean_id=source.id, bean_id=card.id, status="created"))

        created_count = sum(1 for item in items if item.status == "created")
        existing_count = sum(1 for item in items if item.status == "existing")
        return BeanSquareImportResponse(items=items, created_count=created_count, existing_count=existing_count)

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

        # 豆子相关字段已归一到豆源:优先用 bean_components;否则把顶层 per-bean 字段(老客户端)折成 1 条。
        legacy_keys = (
            "origin_name",
            "process_name",
            "varietal_names",
            "coffee_source_name",
            "green_bean_merchant_name",
            "green_bean_product_name",
            "altitude_text",
            "harvest_date_text",
        )
        legacy = {k: updates.pop(k, None) for k in legacy_keys if k in updates}
        if "bean_components" in updates:
            updates["bean_components"] = [
                c.model_dump(exclude_none=True) for c in (payload.bean_components or [])
            ]
        elif legacy:
            folded = {
                "origin_name": _clean_text(legacy.get("origin_name")),
                "coffee_source_name": _clean_text(legacy.get("coffee_source_name")),
                "green_bean_merchant_name": _clean_text(legacy.get("green_bean_merchant_name")),
                "green_bean_product_name": _clean_text(legacy.get("green_bean_product_name")),
                "process_name": _clean_text(legacy.get("process_name")),
                "varietal_names": list(legacy.get("varietal_names") or []),
                "altitude_text": _clean_text(legacy.get("altitude_text")),
                "harvest_date_text": _clean_text(legacy.get("harvest_date_text")),
            }
            updates["bean_components"] = [{k: v for k, v in folded.items() if v}] if any(folded.values()) else []

        for key, value in updates.items():
            setattr(card, key, value)
        await session.flush()
        await self._link_entities(session, card)  # 重新逐豆源回填 + 刷新 bean_product_type
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
