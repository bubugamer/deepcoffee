"""候选事实抽取（自下而上数据流的第一步）。

从用户**确认后的私有豆卡**里，把可复用的公共实体事实片段（烘焙商、产地、处理法、品种、
生豆商、生产者/庄园、烘焙商产品、生豆商产品…）抽出来，生成候选事实，进入管理员审核链路。

边界（对齐 backend-plan 的「AI 写入边界」）：
- 只抽**客观公共实体事实**；用户主观冲煮理念、口味判断、经验总结、私有风味理念不抽。
- 去重：该实体已在公共实体库（active）或已有未关闭候选时，不重复生成。
- 候选只是「待审」，不直接成为公共知识，必须经管理员审核 → 提案 → 公共实体库。
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import PublicEntity as PublicEntityORM
from app.models.tables import UserBeanCard as UserBeanCardORM
from app.repositories.candidates import candidate_repository
from app.repositories.entities import entity_repository
from app.repositories.proposals import proposal_repository

logger = logging.getLogger(__name__)


class CandidateService:
    async def extract_from_bean(
        self, session: AsyncSession, *, user_id: str, bean_id: str, trace_id: str | None = None
    ) -> list[str]:
        """返回生成的候选 id 列表。失败只记日志、不抛（不阻断豆卡建档）。"""
        card = await session.get(UserBeanCardORM, bean_id)
        if card is None:
            return []

        # (entity_type, 名称, 额外 payload) 的候选清单。顶层只剩产品级(roaster/roaster_product);
        # 豆子相关实体名(产地/处理法/庄园/生豆商/生豆商产品/品种)都在「豆源」里,逐条产候选。
        facts: list[tuple[str, str, dict]] = []
        if card.roaster_name:
            facts.append(("roaster", card.roaster_name, {"name": card.roaster_name}))
        if card.roaster_product_name:
            facts.append(
                (
                    "roaster_product",
                    card.roaster_product_name,
                    {"name": card.roaster_product_name, "product_name": card.roaster_product_name,
                     "roaster": card.roaster_name},
                )
            )
        for component in card.bean_components or []:
            if not isinstance(component, dict):
                continue
            origin = component.get("origin_name")
            if isinstance(origin, str) and origin.strip():
                facts.append(("origin", origin.strip(), {"name": origin.strip()}))
            process = component.get("process_name")
            if isinstance(process, str) and process.strip():
                facts.append(("process_method", process.strip(), {"name": process.strip()}))
            source = component.get("coffee_source_name")
            if isinstance(source, str) and source.strip():
                facts.append(("coffee_source", source.strip(), {"name": source.strip()}))
            merchant = component.get("green_bean_merchant_name")
            if isinstance(merchant, str) and merchant.strip():
                facts.append(("green_bean_merchant", merchant.strip(), {"name": merchant.strip()}))
            gb_product = component.get("green_bean_product_name")
            if isinstance(gb_product, str) and gb_product.strip():
                facts.append(
                    ("green_bean_product", gb_product.strip(),
                     {"name": gb_product.strip(), "lot_name": gb_product.strip()})
                )
            varietals = component.get("varietal_names")
            if isinstance(varietals, list):
                for varietal in varietals:
                    if isinstance(varietal, str) and varietal.strip():
                        facts.append(("varietal", varietal.strip(), {"name": varietal.strip()}))

        created: list[str] = []
        for entity_type, name, payload in facts:
            try:
                if await entity_repository.exists_active(session, entity_type, name):
                    continue
                if await candidate_repository.has_open(session, entity_type, name):
                    continue
                candidate = await candidate_repository.create(
                    session,
                    entity_type=entity_type,
                    title=name,
                    payload=payload,
                    source_table="user_bean_cards",
                    source_record_id=bean_id,
                    source_user_id=user_id,
                    source_input=card.raw_input,
                    trace_id=trace_id,
                )
                created.append(candidate.id)
            except Exception as exc:  # noqa: BLE001 — 候选生成不阻断建档
                logger.warning("candidate extract failed for %s '%s': %s", entity_type, name, exc)
        return created

    async def promote_to_proposal(
        self, session: AsyncSession, candidate_id: str, *, reviewer_id: str, note: str | None = None
    ) -> tuple[str, str] | None:
        """管理员把候选事实推成公共实体提案。返回 (candidate_id, proposal_id)。

        候选 → 提案 → （提案 approve/mark-applied）→ 公共实体库，复用同一套提案审核 UI。
        """
        candidate = await candidate_repository.get_orm(session, candidate_id)
        if candidate is None:
            return None
        proposal = await proposal_repository.create(
            session,
            entity_type=candidate.entity_type,
            title=candidate.title,
            payload=dict(candidate.payload or {}),
            source_input=candidate.source_input,
            trace_id=candidate.trace_id,
            proposer_id=candidate.source_user_id or reviewer_id,
        )
        await candidate_repository.mark_promoted(
            session, candidate_id, proposal_id=proposal.id, reviewer_id=reviewer_id
        )
        return candidate_id, proposal.id

    async def merge_candidate_into_entity(
        self,
        session: AsyncSession,
        candidate_id: str,
        *,
        entity_id: str,
        reviewer_id: str,
        note: str | None = None,
    ):
        """管理员把候选「并入」已有实体：候选名登记为该实体别名（source='admin'），候选标记 merged，
        不建新实体。专治缩写/中英等需人工判断的重复（如 SEY → SEY Coffee）。"""
        candidate = await candidate_repository.get_orm(session, candidate_id)
        if candidate is None:
            return None
        entity = await session.get(PublicEntityORM, entity_id)
        if entity is None:
            return None
        await entity_repository.register_aliases(session, entity_id, candidate.title, source="admin")
        return await candidate_repository.merge_into(
            session, candidate_id, entity_id=entity_id, reviewer_id=reviewer_id, note=note
        )


candidate_service = CandidateService()
