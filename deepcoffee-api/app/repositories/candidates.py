from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import CandidateFact as CandidateFactORM
from app.models.tables import UserProfile
from app.repositories.entities import canonical_type, normalize_name
from app.schemas.candidate import CandidateFact

# 候选事实里仍待审核的状态（用于去重，避免对同一实体反复生成候选）。
_OPEN_STATUSES = ("pending_review", "promoted")


class CandidateRepository:
    async def _existing_profile_id(self, session: AsyncSession, user_id: str | None) -> str | None:
        # source_user_id / reviewer_id 有 FK→user_profiles；未建档（dev token）则置 None。
        if not user_id:
            return None
        return user_id if await session.get(UserProfile, user_id) else None

    async def has_open(self, session: AsyncSession, entity_type: str, name: str) -> bool:
        # 单查询取回同类型未关闭候选的 title，在内存里按归一名比对（避免 N+1）。
        result = await session.execute(
            select(CandidateFactORM.title).where(
                CandidateFactORM.entity_type == canonical_type(entity_type),
                CandidateFactORM.status.in_(_OPEN_STATUSES),
            )
        )
        target = normalize_name(name)
        return any(normalize_name(title) == target for (title,) in result.all())

    async def create(
        self,
        session: AsyncSession,
        *,
        entity_type: str,
        title: str,
        payload: dict[str, Any],
        source_table: str | None,
        source_record_id: str | None,
        source_user_id: str | None,
        source_input: str | None = None,
        fact_type: str | None = None,
        trace_id: str | None = None,
    ) -> CandidateFact:
        row = CandidateFactORM(
            id=f"cand_{uuid4().hex[:12]}",
            entity_type=canonical_type(entity_type),
            fact_type=fact_type,
            title=title,
            payload=payload,
            source_scope="private",
            source_table=source_table,
            source_record_id=source_record_id,
            source_user_id=await self._existing_profile_id(session, source_user_id),
            source_input=source_input,
            status="pending_review",
            trace_id=trace_id,
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return CandidateFact.model_validate(row)

    async def list(
        self, session: AsyncSession, *, status: str | None = None, entity_type: str | None = None
    ) -> list[CandidateFact]:
        conditions = []
        if status:
            conditions.append(CandidateFactORM.status == status)
        if entity_type:
            conditions.append(CandidateFactORM.entity_type == canonical_type(entity_type))
        result = await session.execute(
            select(CandidateFactORM).where(*conditions).order_by(CandidateFactORM.created_at.desc())
        )
        return [CandidateFact.model_validate(row) for row in result.scalars().all()]

    async def get_orm(self, session: AsyncSession, candidate_id: str) -> CandidateFactORM | None:
        return await session.get(CandidateFactORM, candidate_id)

    async def reject(
        self, session: AsyncSession, candidate_id: str, *, reviewer_id: str, note: str | None
    ) -> CandidateFact | None:
        row = await session.get(CandidateFactORM, candidate_id)
        if row is None:
            return None
        row.status = "rejected"
        row.reviewer_id = await self._existing_profile_id(session, reviewer_id)
        row.reviewer_note = note
        row.reviewed_at = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(row)
        return CandidateFact.model_validate(row)

    async def mark_promoted(
        self, session: AsyncSession, candidate_id: str, *, proposal_id: str, reviewer_id: str
    ) -> CandidateFact | None:
        row = await session.get(CandidateFactORM, candidate_id)
        if row is None:
            return None
        row.status = "promoted"
        row.proposal_id = proposal_id
        row.reviewer_id = await self._existing_profile_id(session, reviewer_id)
        row.reviewed_at = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(row)
        return CandidateFact.model_validate(row)


candidate_repository = CandidateRepository()
