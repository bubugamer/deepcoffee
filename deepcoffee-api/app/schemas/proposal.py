from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ProposalStatus = Literal["pending", "approved", "rejected", "applied"]


class ProposalCreateRequest(BaseModel):
    entity_type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    payload: dict[str, Any]
    source_input: str | None = Field(default=None, max_length=4000)
    trace_id: str | None = Field(default=None, max_length=120)


class ProposalReviewRequest(BaseModel):
    reviewer_note: str | None = Field(default=None, max_length=1000)


class ProposalMarkAppliedRequest(BaseModel):
    applied_markdown_path: str | None = Field(default=None, max_length=500)
    reviewer_note: str | None = Field(default=None, max_length=1000)


class ProposalAuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action: str
    actor_id: str
    note: str | None = None
    created_at: datetime


class Proposal(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    title: str
    payload: dict[str, Any]
    source_input: str | None
    trace_id: str | None
    proposer_id: str
    status: ProposalStatus
    reviewer_note: str | None = None
    applied_entity_id: str | None = None
    applied_markdown_path: str | None = None
    created_at: datetime
    updated_at: datetime
    audit: list[ProposalAuditEntry]


class ProposalCreateResponse(BaseModel):
    proposal_id: str
    status: ProposalStatus
