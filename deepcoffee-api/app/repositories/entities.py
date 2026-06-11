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

    async def exists_active(self, session: AsyncSession, entity_type: str, name: str) -> bool:
        existing = await self.get_by_type_name(session, entity_type, name)
        return existing is not None and existing.status == "active"

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
        existing = await self.get_by_type_name(session, etype, canonical_name)
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
