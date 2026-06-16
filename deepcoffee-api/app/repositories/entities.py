"""公共实体库写入与读取。

提案审核通过后由这里把提案 payload **物化**成 `public_entities` + 对应分类表行（幂等，
按 (entity_type, normalized_name) 去重）。模型/用户都不能直接写这些最终表——只能经提案。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import (
    CoffeeSource,
    EntityAlias,
    GreenBeanMerchant,
    GreenBeanProduct,
    Origin,
    ProcessMethod,
    PublicEntity as PublicEntityORM,
    Roaster,
    RoasterProduct,
    UserProfile,
    Varietal,
)
from app.schemas.entity import PublicEntity

# 提案/候选 entity_type 归一到一套规范类型。
_TYPE_ALIASES = {
    "roaster": "roaster",
    "烘焙商": "roaster",
    "coffee_source": "coffee_source",
    "producer": "coffee_source",
    "estate": "coffee_source",
    "庄园": "coffee_source",
    "处理站": "coffee_source",
    "washing_station": "coffee_source",
    "green_bean_merchant": "green_bean_merchant",
    "green_merchant": "green_bean_merchant",
    "生豆商": "green_bean_merchant",
    "importer": "green_bean_merchant",
    "进口商": "green_bean_merchant",
    "origin": "origin",
    "产地": "origin",
    "varietal": "varietal",
    "variety": "varietal",
    "品种": "varietal",
    "process": "process_method",
    "process_method": "process_method",
    "处理法": "process_method",
    "roaster_product": "roaster_product",
    "烘焙商产品": "roaster_product",
    "green_bean_product": "green_bean_product",
    "生豆商产品": "green_bean_product",
}


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").strip().lower()
    return re.sub(r"\s+", " ", value)


def disambig_key(value: str) -> str:
    """形态归一 key：在 normalize_name 基础上再去空格与常见分隔标点，用于「大小写/空格/全半角」
    差异的自动认同（coffee buff / Coffeebuff / Coffee Buff → coffeebuff）。"""
    s = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[\s\-_/／、，,.。·|｜]+", "", s)


# 主名里中英 / 多名常用分隔符；据此拆出可独立匹配的片段（如 "Captain George / 乔治队长"）。
_NAME_SPLIT_RE = re.compile(r"\s*[/／|｜、]\s*")


def alias_fragments(canonical_name: str) -> list[str]:
    """把主名拆成可独立匹配的片段（含整名本身），用于自动建别名。"""
    whole = (canonical_name or "").strip()
    parts = [p.strip() for p in _NAME_SPLIT_RE.split(whole) if p.strip()]
    out: list[str] = []
    for p in [whole, *parts]:
        if p and p not in out:
            out.append(p)
    return out


def canonical_type(entity_type: str) -> str:
    return _TYPE_ALIASES.get((entity_type or "").strip().lower(), (entity_type or "").strip().lower())


class EntityRepository:
    async def get_by_type_name(
        self, session: AsyncSession, entity_type: str, name: str
    ) -> PublicEntityORM | None:
        result = await session.execute(
            select(PublicEntityORM).where(
                PublicEntityORM.entity_type == canonical_type(entity_type),
                PublicEntityORM.normalized_name == normalize_name(name),
            )
        )
        return result.scalar_one_or_none()

    async def resolve_entity(
        self, session: AsyncSession, entity_type: str, name: str
    ) -> PublicEntityORM | None:
        """统一实体匹配：先 canonical normalized_name 精确，再查别名表（normalize_name / disambig_key 两种 key）。

        形态差异（大小写/空格/全半角）经 disambig_key 自动认同；中英双名 / 译名经拆分别名命中。
        缩写 / 子串关系不在此处自动匹配（交审核「疑似并入」）。
        """
        etype = canonical_type(entity_type)
        direct = await self.get_by_type_name(session, etype, name)
        if direct is not None:
            return direct
        keys = {k for k in (normalize_name(name), disambig_key(name)) if k}
        if not keys:
            return None
        result = await session.execute(
            select(PublicEntityORM)
            .join(EntityAlias, EntityAlias.entity_id == PublicEntityORM.id)
            .where(
                PublicEntityORM.entity_type == etype,
                EntityAlias.normalized_alias.in_(keys),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def register_aliases(
        self,
        session: AsyncSession,
        entity_id: str,
        canonical_name: str,
        *,
        extra: list[str] | None = None,
        source: str = "auto",
    ) -> None:
        """为实体登记匹配别名：主名 + 斜杠/顿号拆分片段 + 额外别名，各按 normalize_name 与 disambig_key 写入。

        幂等：同 (entity_id, normalized_alias) 已存在则跳过。别名表是所有匹配的统一索引（见 resolve_entity）。
        """
        names = alias_fragments(canonical_name)
        for item in extra or []:
            if isinstance(item, str) and item.strip() and item.strip() not in names:
                names.append(item.strip())
        keys: dict[str, str] = {}
        for nm in names:
            for key in (normalize_name(nm), disambig_key(nm)):
                if key:
                    keys.setdefault(key, nm)
        if not keys:
            return
        rows = await session.execute(
            select(EntityAlias.normalized_alias).where(EntityAlias.entity_id == entity_id)
        )
        have = {row[0] for row in rows.all()}
        for nkey, alias in keys.items():
            if nkey in have:
                continue
            session.add(
                EntityAlias(entity_id=entity_id, alias=alias, normalized_alias=nkey, source=source)
            )
        await session.flush()

    async def exists_active(self, session: AsyncSession, entity_type: str, name: str) -> bool:
        existing = await self.resolve_entity(session, entity_type, name)
        return existing is not None and existing.status == "active"

    async def find_similar(
        self, session: AsyncSession, entity_type: str, name: str, *, limit: int = 5
    ) -> list[PublicEntityORM]:
        """找「疑似已有实体」供审核人工判断（不自动合）。

        包含：① resolve_entity 精确/别名/形态命中；② canonical 的 disambig 形态与现有实体
        互为子串（覆盖缩写↔全称，如 SEY ↔ SEY Coffee）。子串只作提示，是否并入由管理员决定。
        """
        etype = canonical_type(entity_type)
        out: list[PublicEntityORM] = []
        hit = await self.resolve_entity(session, etype, name)
        if hit is not None:
            out.append(hit)
        dk = disambig_key(name)
        if dk and len(dk) >= 2:
            rows = await session.execute(
                select(PublicEntityORM).where(
                    PublicEntityORM.entity_type == etype,
                    PublicEntityORM.status == "active",
                )
            )
            seen = {e.id for e in out}
            for e in rows.scalars().all():
                if e.id in seen:
                    continue
                ek = disambig_key(e.canonical_name)
                if ek and len(ek) >= 2 and (dk in ek or ek in dk):
                    out.append(e)
                    if len(out) >= limit:
                        break
        return out[:limit]

    async def _existing_profile_id(self, session: AsyncSession, user_id: str | None) -> str | None:
        if not user_id:
            return None
        return user_id if await session.get(UserProfile, user_id) else None

    def _create_typed_row(self, etype: str, entity_id: str, payload: dict[str, Any]) -> object | None:
        """按类型建分类表行，只取 payload 里出现的已知字段。

        payload 的键既来自提案 payload，也来自 markdown 种子导入器（见
        ``entity_seed_importer``）；缺失的字段一律 None / 空容器，不编造。
        """
        if etype == "roaster":
            return Roaster(
                entity_id=entity_id,
                country=payload.get("country"),
                region=payload.get("region") or payload.get("city"),
                website_url=payload.get("website_url") or payload.get("website"),
                roaster_subtype=payload.get("roaster_subtype"),
                market=payload.get("market"),
                social_links=payload.get("social_links") or {},
                notes=payload.get("notes"),
            )
        if etype == "coffee_source":
            return CoffeeSource(
                entity_id=entity_id,
                source_type=payload.get("source_type") or payload.get("coffee_source_type") or "producer",
                country=payload.get("country"),
                region=payload.get("region"),
                subregion=payload.get("subregion"),
                altitude_m_min=payload.get("altitude_m_min"),
                altitude_m_max=payload.get("altitude_m_max"),
                notes=payload.get("notes"),
            )
        if etype == "green_bean_merchant":
            return GreenBeanMerchant(
                entity_id=entity_id,
                country=payload.get("country"),
                region=payload.get("region"),
                website_url=payload.get("website_url") or payload.get("website"),
                merchant_type=payload.get("merchant_type"),
                social_links=payload.get("social_links") or {},
                notes=payload.get("notes"),
            )
        if etype == "origin":
            return Origin(
                entity_id=entity_id,
                country=payload.get("country"),
                region=payload.get("region"),
                subregion=payload.get("subregion"),
                altitude_m_min=payload.get("altitude_m_min"),
                altitude_m_max=payload.get("altitude_m_max"),
                notes=payload.get("notes"),
            )
        if etype == "varietal":
            return Varietal(
                entity_id=entity_id,
                lineage=payload.get("lineage"),
                species=payload.get("species"),
                description=payload.get("description"),
            )
        if etype == "process_method":
            return ProcessMethod(
                entity_id=entity_id,
                process_group=payload.get("process_group"),
                description=payload.get("description"),
            )
        if etype == "roaster_product":
            return RoasterProduct(
                entity_id=entity_id,
                roaster_entity_id=payload.get("roaster_entity_id"),
                roaster_name=payload.get("roaster_name"),
                product_type=payload.get("product_type"),
                product_name=payload.get("product_name"),
                product_url=payload.get("product_url"),
                official_flavor_notes=payload.get("official_flavor_notes") or [],
                official_brew_params=payload.get("official_brew_params") or {},
            )
        if etype == "green_bean_product":
            return GreenBeanProduct(
                entity_id=entity_id,
                merchant_entity_id=payload.get("merchant_entity_id"),
                merchant_name=payload.get("merchant_name"),
                product_type=payload.get("product_type"),
                lot_name=payload.get("lot_name"),
                batch_code=payload.get("batch_code"),
                crop_year=payload.get("crop_year"),
                harvest_season=payload.get("harvest_season"),
                product_url=payload.get("product_url"),
                cupping_notes=payload.get("cupping_notes") or [],
            )
        return None

    async def upsert(
        self,
        session: AsyncSession,
        *,
        entity_type: str,
        canonical_name: str,
        payload: dict[str, Any] | None = None,
        summary: str | None = None,
        created_from: str = "proposal",
        created_by: str | None = None,
        reviewed_by: str | None = None,
    ) -> PublicEntity:
        """幂等写入公共实体（含分类表）。已存在则返回既有实体。"""
        etype = canonical_type(entity_type)
        payload = payload or {}
        existing = await self.resolve_entity(session, etype, canonical_name)
        if existing is not None:
            return PublicEntity.model_validate(existing)

        # created_by/reviewed_by 有 FK→user_profiles；提案者/管理员未必建过档（dev token 用户），
        # 不存在就置 None，避免外键冲突（provenance 仍由 created_from + 提案 proposer_id 记录）。
        created_by = await self._existing_profile_id(session, created_by)
        reviewed_by = await self._existing_profile_id(session, reviewed_by)

        entity = PublicEntityORM(
            id=f"ent_{uuid4().hex[:12]}",
            entity_type=etype,
            canonical_name=canonical_name,
            normalized_name=normalize_name(canonical_name),
            scope="public",
            status="active",
            summary=summary,
            created_from=created_from,
            created_by=created_by,
            reviewed_by=reviewed_by,
        )
        session.add(entity)
        await session.flush()
        # 自动登记匹配别名（主名拆分 + 形态 key）；payload.aliases 若有则一并登记。
        await self.register_aliases(session, entity.id, canonical_name, extra=payload.get("aliases"))
        typed = self._create_typed_row(etype, entity.id, payload)
        if typed is not None:
            session.add(typed)
            await session.flush()
        return PublicEntity.model_validate(entity)

    async def materialize_from_proposal(self, session: AsyncSession, proposal: Any) -> PublicEntity:
        payload = dict(proposal.payload or {})
        name = payload.get("name") or payload.get("canonical_name") or proposal.title
        return await self.upsert(
            session,
            entity_type=proposal.entity_type,
            canonical_name=name,
            payload=payload,
            summary=payload.get("summary"),
            created_from="proposal",
            created_by=proposal.proposer_id,
        )

    async def list(
        self,
        session: AsyncSession,
        *,
        entity_type: str | None = None,
        status: str | None = None,
    ) -> list[PublicEntity]:
        conditions = []
        if entity_type:
            conditions.append(PublicEntityORM.entity_type == canonical_type(entity_type))
        if status:
            conditions.append(PublicEntityORM.status == status)
        result = await session.execute(
            select(PublicEntityORM).where(*conditions).order_by(PublicEntityORM.created_at.desc())
        )
        return [PublicEntity.model_validate(row) for row in result.scalars().all()]

    async def count(self, session: AsyncSession, *, status: str = "active") -> int:
        result = await session.execute(
            select(func.count()).select_from(PublicEntityORM).where(PublicEntityORM.status == status)
        )
        return int(result.scalar_one())


entity_repository = EntityRepository()
