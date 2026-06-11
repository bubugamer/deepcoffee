from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Proposal as ProposalORM
from app.models.tables import ProposalAuditEvent as ProposalAuditEventORM
from app.schemas.proposal import Proposal


class ProposalRepository:
    async def _load(self, session: AsyncSession, proposal_id: str) -> ProposalORM | None:
        result = await session.execute(select(ProposalORM).where(ProposalORM.id == proposal_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        session: AsyncSession,
        *,
        entity_type: str,
        title: str,
        payload: dict[str, Any],
        source_input: str | None,
        trace_id: str | None,
        proposer_id: str,
    ) -> Proposal:
        proposal_id = f"prop_{uuid4().hex[:12]}"
        proposal = ProposalORM(
            id=proposal_id,
            entity_type=entity_type,
            title=title,
            payload=payload,
            source_input=source_input,
            trace_id=trace_id,
            proposer_id=proposer_id,
            status="pending",
            audit=[ProposalAuditEventORM(actor_id=proposer_id, action="created")],
        )
        session.add(proposal)
        await session.flush()
        loaded = await self._load(session, proposal_id)
        return Proposal.model_validate(loaded)

    async def list(
        self, session: AsyncSession, *, status: str | None = None, entity_type: str | None = None
    ) -> list[Proposal]:
        conditions = []
        if status:
            conditions.append(ProposalORM.status == status)
        if entity_type:
            conditions.append(ProposalORM.entity_type == entity_type)
        result = await session.execute(
            select(ProposalORM).where(*conditions).order_by(ProposalORM.created_at.desc())
        )
        return [Proposal.model_validate(row) for row in result.scalars().all()]

    async def get(self, session: AsyncSession, proposal_id: str) -> Proposal | None:
        row = await self._load(session, proposal_id)
        return Proposal.model_validate(row) if row else None

    async def transition(
        self,
        session: AsyncSession,
        proposal_id: str,
        *,
        status: str,
        actor_id: str,
        note: str | None = None,
        applied_markdown_path: str | None = None,
        applied_entity_id: str | None = None,
    ) -> Proposal | None:
        row = await self._load(session, proposal_id)
        if row is None:
            return None
        row.status = status
        if note:
            row.reviewer_note = note
        if applied_markdown_path:
            row.applied_markdown_path = applied_markdown_path
        if applied_entity_id:
            row.applied_entity_id = applied_entity_id
        row.audit.append(ProposalAuditEventORM(actor_id=actor_id, action=status, note=note))
        await session.flush()
        refreshed = await self._load(session, proposal_id)
        return Proposal.model_validate(refreshed)


proposal_repository = ProposalRepository()
