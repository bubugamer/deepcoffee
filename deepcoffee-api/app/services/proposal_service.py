from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.repositories.entities import entity_repository
from app.repositories.proposals import proposal_repository
from app.schemas.proposal import Proposal
from app.services.knowledge_sync_service import knowledge_sync_service


class ProposalService:
    async def list(
        self, session: AsyncSession, status: str | None = None, entity_type: str | None = None
    ) -> list[Proposal]:
        return await proposal_repository.list(session, status=status, entity_type=entity_type)

    async def get(self, session: AsyncSession, proposal_id: str) -> Proposal:
        proposal = await proposal_repository.get(session, proposal_id)
        if not proposal:
            raise AppError(404, "proposal_not_found", "Proposal not found.")
        return proposal

    async def transition(
        self,
        session: AsyncSession,
        proposal_id: str,
        *,
        status: str,
        actor_id: str,
        note: str | None = None,
        applied_markdown_path: str | None = None,
    ) -> Proposal:
        current = await proposal_repository.get(session, proposal_id)
        if not current:
            raise AppError(404, "proposal_not_found", "Proposal not found.")

        # 批准 / 应用：把提案 payload 物化进公共实体库（幂等），记下 applied_entity_id。
        # 批准 = 进入公共实体库但不动 Markdown；应用 = 再跑知识库同步管线写/更 Markdown。
        applied_entity_id: str | None = None
        if status in ("approved", "applied"):
            entity = await entity_repository.materialize_from_proposal(session, current)
            applied_entity_id = entity.id

        proposal = await proposal_repository.transition(
            session,
            proposal_id,
            status=status,
            actor_id=actor_id,
            note=note,
            applied_markdown_path=applied_markdown_path,
            applied_entity_id=applied_entity_id,
        )
        if not proposal:
            raise AppError(404, "proposal_not_found", "Proposal not found.")

        if status == "applied" and applied_entity_id:
            await knowledge_sync_service.sync_entity(
                session, applied_entity_id, markdown_path=applied_markdown_path
            )
        return proposal


proposal_service = ProposalService()
