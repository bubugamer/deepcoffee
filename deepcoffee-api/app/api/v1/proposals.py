from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_member
from app.core.db import get_session
from app.core.security import AuthenticatedUser, get_current_user
from app.repositories.proposals import proposal_repository
from app.schemas.proposal import ProposalCreateRequest, ProposalCreateResponse

router = APIRouter(prefix="/proposals", tags=["proposals"], dependencies=[Depends(require_member)])


@router.post("", response_model=ProposalCreateResponse)
async def create_proposal(
    payload: ProposalCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProposalCreateResponse:
    proposal = await proposal_repository.create(
        session,
        entity_type=payload.entity_type,
        title=payload.title,
        payload=payload.payload,
        source_input=payload.source_input,
        trace_id=payload.trace_id,
        proposer_id=user.id,
    )
    return ProposalCreateResponse(proposal_id=proposal.id, status=proposal.status)
